"""
Standalone script: embed Hebrew messages → HDBSCAN clusters → keyword report.
Goal: manually derive a categories gazetteer for activities in the messages.

Run from the project root:
    python scrap/cluster_messages.py [--min-cluster-size N] [--samples K]
"""

import sys
import os
import re
import argparse
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from models.base import engine
from models.message import Message
from sqlalchemy import select
from bidi.algorithm import get_display


WIDTH = 80


def rtl(text):
    """Reshape Hebrew text so it renders left-to-right in a terminal."""
    return get_display(str(text))


HEBREW_STOP_WORDS = {
    "של", "את", "על", "עם", "אל", "לא", "כי", "הם", "הן", "הוא", "היא",
    "אנחנו", "אני", "אתה", "זה", "זו", "זאת", "אבל", "גם", "כן", "רק",
    "עוד", "כבר", "מה", "מי", "איפה", "מתי", "למה", "כיצד", "אם", "כש",
    "כאשר", "אחרי", "לפני", "בין", "תחת", "מעל", "מתחת", "ליד",
    "אחד", "שתי", "שני", "שלוש", "ארבע", "חמש",
    "היה", "הייתה", "יש", "אין", "כל", "כלל", "שם", "פה", "כאן", "שוב",
    "בו", "בה", "בהם", "לו", "לה", "להם", "מהם", "מהן",
    "שלו", "שלה", "שלהם", "שלנו", "שלי", "שלך",
    "אותו", "אותה", "אותם", "אותן",
    "ה", "ו", "ב", "ל", "מ", "כ",
}


def load_messages(limit=None):
    with Session(engine) as session:
        stmt = select(Message.id, Message.text, Message.channel)
        if limit:
            stmt = stmt.limit(limit)
        rows = session.execute(stmt).all()
    return [(r.id, r.text, r.channel) for r in rows if r.text and r.text.strip()]


def tokenize_hebrew(text):
    text = re.sub(r"[^א-ת\s]", " ", text)
    return [w for w in text.split() if len(w) > 1 and w not in HEBREW_STOP_WORDS]


def embed_texts(texts, model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
    from sentence_transformers import SentenceTransformer
    print(f"  model : {model_name}", flush=True)
    model = SentenceTransformer(model_name)
    print(f"  texts : {len(texts)}", flush=True)
    return model.encode(texts, batch_size=64, show_progress_bar=True, normalize_embeddings=True)


def run_hdbscan(embeddings, min_cluster_size, min_samples):
    import hdbscan
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    return clusterer.fit_predict(embeddings)


def build_tfidf(all_texts):
    from sklearn.feature_extraction.text import TfidfVectorizer
    vectorizer = TfidfVectorizer(
        tokenizer=tokenize_hebrew,
        token_pattern=None,
        max_features=5000,
        sublinear_tf=True,
    )
    vectorizer.fit(all_texts)
    return vectorizer


def top_keywords(vectorizer, cluster_texts, top_n=12):
    terms = vectorizer.get_feature_names_out()
    vec = vectorizer.transform([" ".join(cluster_texts)]).toarray()[0]
    top_idx = np.argsort(vec)[::-1][:top_n]
    return [terms[i] for i in top_idx if vec[i] > 0]


def hr(char="─"):
    print(char * WIDTH)


def print_report(ids, texts, channels, labels, vectorizer, samples_per_cluster):
    unique_labels = sorted(set(labels))
    n_clusters = sum(1 for l in unique_labels if l >= 0)
    n_noise = sum(1 for l in labels if l == -1)

    print()
    hr("═")
    print(f"  CLUSTERING REPORT")
    print(f"  messages : {len(texts)}")
    print(f"  clusters : {n_clusters}")
    print(f"  noise    : {n_noise}  ({100 * n_noise / len(texts):.1f}%)")
    hr("═")

    for label in unique_labels:
        mask = [i for i, l in enumerate(labels) if l == label]

        print()
        hr()

        if label == -1:
            print(f"  NOISE / UNCLUSTERED  —  {len(mask)} messages")
            continue

        cluster_texts = [texts[i] for i in mask]
        cluster_channels = [channels[i] for i in mask]

        channel_counts = {}
        for ch in cluster_channels:
            channel_counts[ch] = channel_counts.get(ch, 0) + 1
        top_channels = sorted(channel_counts.items(), key=lambda x: -x[1])[:3]
        channels_str = "  ".join(f"{rtl(c)} ({n})" for c, n in top_channels)

        print(f"  CLUSTER {label}  —  {len(mask)} messages")
        print(f"  channels : {channels_str}")

        keywords = top_keywords(vectorizer, cluster_texts)
        print(f"  keywords :")
        # Print keywords in rows of 4, each right-to-left
        for row_start in range(0, len(keywords), 4):
            row = keywords[row_start:row_start + 4]
            print("    " + "    ".join(rtl(w) for w in row))

        n_samples = min(samples_per_cluster, len(mask))
        print(f"\n  samples ({n_samples} of {len(mask)}) :")
        for i in mask[:n_samples]:
            # Collapse newlines and trim
            raw = texts[i].replace("\n", " ").strip()
            display = rtl(raw[:220])
            print(f"    [{ids[i]:>5}]  {display}")

    print()
    hr("═")
    print()


def main():
    parser = argparse.ArgumentParser(description="Cluster Hebrew messages for gazetteer building")
    parser.add_argument("--min-cluster-size", type=int, default=5)
    parser.add_argument("--min-samples",      type=int, default=3)
    parser.add_argument("--limit",            type=int, default=None,
                        help="Max messages to load (default: all)")
    parser.add_argument("--samples",          type=int, default=5,
                        help="Sample messages per cluster (default: 5)")
    args = parser.parse_args()

    print("\nLoading messages ...", flush=True)
    rows = load_messages(args.limit)
    if not rows:
        print("No messages found. Run the scraper first.")
        sys.exit(1)

    ids      = [r[0] for r in rows]
    texts    = [r[1] for r in rows]
    channels = [r[2] for r in rows]

    print("\nEmbedding ...", flush=True)
    embeddings = embed_texts(texts)

    print(f"\nClustering  (min_cluster_size={args.min_cluster_size}, "
          f"min_samples={args.min_samples}) ...", flush=True)
    labels = run_hdbscan(embeddings, args.min_cluster_size, args.min_samples)

    print("\nBuilding TF-IDF vocabulary ...", flush=True)
    vectorizer = build_tfidf(texts)

    print_report(ids, texts, channels, labels, vectorizer, args.samples)


if __name__ == "__main__":
    main()
