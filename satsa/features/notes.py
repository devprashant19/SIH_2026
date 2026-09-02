"""Investigation-note quality: missing notes, template/copy-paste detection, relevance."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors

from satsa.features.base import INVESTIGATED_RANK, EntityContext, FeatureMeta, FeatureValue, action_rank, fv, rate

META: list[FeatureMeta] = [
    FeatureMeta("note_missing_rate", "Missing investigation notes", "notes", "n(note null or < 10 chars | action >= INVESTIGATED) / n(action >= INVESTIGATED)", 20, True, headline=True),
    FeatureMeta("note_len_median", "Median note length", "notes", "median(len(note))", 10, False, "chars"),
    FeatureMeta("note_len_cv", "Note length variability", "notes", "std(len)/mean(len)", 10, False),
    FeatureMeta("note_template_score", "Note templating score", "notes", "mean_i max_{j!=i} cos(tfidf_i, tfidf_j)", 25, True, headline=True),
    FeatureMeta("note_dup_cluster_share", "Near-duplicate note share", "notes", "share of notes with >= 5 neighbours at cos > 0.9", 25, True, headline=True),
    FeatureMeta("note_distinct_ratio", "Distinct note ratio", "notes", "n(distinct normalised notes) / n(notes)", 25, False, headline=True),
    FeatureMeta("note_alert_relevance", "Note-to-alert relevance", "notes", "mean cos(tfidf(note), tfidf(category + rule + asset class))", 25, False),
    FeatureMeta("note_len_ttc_corr", "Note length vs closure time", "notes", "spearman(len(note), ttc)", 25, False),
]

_ID_RE = re.compile(r"[0-9a-f]{8,}|\d+|[\w.-]+@[\w.-]+|\b[a-z0-9-]+\.(?:local|com|net|org)\b", re.I)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", _ID_RE.sub("#", text.lower())).strip()


def compute(ctx: EntityContext) -> dict[str, FeatureValue]:
    a = ctx.alerts
    investigated = a[action_rank(a["analyst_action"]) >= INVESTIGATED_RANK]
    n_inv = len(investigated)
    notes_raw = investigated["investigation_notes"].fillna("").astype(str).str.strip()
    missing = notes_raw.str.len() < 10
    out: dict[str, FeatureValue] = {"note_missing_rate": fv(rate(missing.sum(), n_inv), n_inv, 20)}

    with_notes = investigated[~missing.values]
    notes = with_notes["investigation_notes"].astype(str).str.strip()
    m = len(notes)
    lengths = notes.str.len()
    out["note_len_median"] = fv(lengths.median() if m else None, m, 10)
    out["note_len_cv"] = fv((lengths.std(ddof=0) / lengths.mean()) if m >= 2 and lengths.mean() > 0 else None, m, 10)
    out["note_distinct_ratio"] = fv(rate(notes.map(_normalise).nunique(), m), m, 25)

    if m < 5:
        for k in ("note_template_score", "note_dup_cluster_share", "note_alert_relevance", "note_len_ttc_corr"):
            out[k] = fv(None, m)
        return out

    cap = ctx.settings.features.max_notes_for_similarity
    sample = with_notes.sample(n=cap, random_state=ctx.settings.app.seed) if m > cap else with_notes
    texts = sample["investigation_notes"].astype(str).tolist()
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=20000, sublinear_tf=True)
    X = vec.fit_transform(texts)

    nn = NearestNeighbors(n_neighbors=min(2, len(texts)), metric="cosine", algorithm="brute").fit(X)
    dist, _ = nn.kneighbors(X)
    max_cos = 1.0 - dist[:, 1] if dist.shape[1] > 1 else np.zeros(len(texts))
    out["note_template_score"] = fv(float(np.mean(max_cos)), m, 25)

    radius = 1.0 - ctx.settings.features.dup_cluster_cosine
    neigh = nn.radius_neighbors(X, radius=radius, return_distance=False)
    min_nb = ctx.settings.features.dup_cluster_min_neighbours
    dup = np.array([len(ix) - 1 >= min_nb for ix in neigh])
    out["note_dup_cluster_share"] = fv(float(dup.mean()), m, 25)

    asset_class = _asset_class_lookup(ctx)
    context_docs = [
        f"{r.category} {str(r.rule_name or '').replace('_', ' ')} {asset_class.get(str(r.asset_id), '')}"
        for r in sample.itertuples()
    ]
    C = vec.transform(context_docs)
    rel = np.asarray(X.multiply(C).sum(axis=1)).ravel()
    out["note_alert_relevance"] = fv(float(rel.mean()), m, 25)

    closed = sample[sample["time_to_close_min"].notna()]
    note_len = closed["investigation_notes"].astype(str).str.len()
    if len(closed) >= 10 and note_len.nunique() > 1 and closed["time_to_close_min"].nunique() > 1:
        rho, _ = spearmanr(note_len, closed["time_to_close_min"].astype(float))
        out["note_len_ttc_corr"] = fv(None if np.isnan(rho) else float(rho), len(closed), 25)
    else:
        out["note_len_ttc_corr"] = fv(None, len(closed))

    # Evidence for EG-05: the most repeated normalised notes and their counts.
    norm_counts = notes.map(_normalise).value_counts().head(3)
    ctx.extras["top_template_notes"] = [{"note": k[:160], "count": int(v)} for k, v in norm_counts.items()]
    template_ids = sample["alert_id"].astype(str).values[max_cos >= ctx.settings.features.template_cosine_threshold]
    ctx.extras["template_note_alert_ids"] = template_ids[:200].tolist()
    return out


def _asset_class_lookup(ctx: EntityContext) -> dict[str, str]:
    if not len(ctx.assets):
        return {}
    return dict(zip(ctx.assets["asset_id"].astype(str), ctx.assets["asset_class"].astype(str).str.lower().str.replace("_", " ")))


def per_alert_template_similarity(alerts: pd.DataFrame) -> pd.Series:
    """Alert-level max cosine to another note in the same frame (used by alert-scope rules)."""
    notes = alerts["investigation_notes"].fillna("").astype(str)
    mask = notes.str.strip().str.len() >= 10
    result = pd.Series(np.nan, index=alerts.index)
    if mask.sum() < 2:
        return result
    X = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True).fit_transform(notes[mask])
    dist, _ = NearestNeighbors(n_neighbors=2, metric="cosine", algorithm="brute").fit(X).kneighbors(X)
    result[mask] = 1.0 - dist[:, 1]
    return result
