"""
Exploratory data analysis of Telegram messages with assigned locations.

Run from project root:
    python scrap/explore_data.py [--out-dir scrap/charts]

Produces PNG charts and a printed summary. Requires: matplotlib, pandas.
    pip install matplotlib
"""

import sys
import os
import argparse
from collections import Counter
from itertools import combinations

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from models.base import engine


# ── data loading ─────────────────────────────────────────────────────────────

def load_data():
    """Return (messages_df, locations_df, msg_loc_df) as raw DataFrames."""
    with engine.connect() as conn:
        messages = pd.read_sql(
            text("SELECT id, timestamp, text, channel FROM messages"),
            conn,
            parse_dates=["timestamp"],
        )
        locations = pd.read_sql(
            text("SELECT id, name_en, name_he, front, lat, lon FROM locations"),
            conn,
        )
        msg_loc = pd.read_sql(
            text("SELECT message_id, location_id FROM message_locations"),
            conn,
        )
    return messages, locations, msg_loc


def build_joined(messages, locations, msg_loc):
    """Return a flat DataFrame: one row per (message, location) pair."""
    joined = (
        msg_loc
        .merge(messages, left_on="message_id", right_on="id", suffixes=("", "_msg"))
        .merge(locations, left_on="location_id", right_on="id", suffixes=("", "_loc"))
    )
    joined["hour"] = joined["timestamp"].dt.hour
    joined["date"] = joined["timestamp"].dt.date
    joined["dow"]  = joined["timestamp"].dt.day_name()
    return joined


# ── helpers ───────────────────────────────────────────────────────────────────

DAYS_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

def savefig(fig, out_dir, name):
    path = os.path.join(out_dir, name)
    fig.savefig(path, bbox_inches="tight", dpi=130)
    plt.close(fig)
    print(f"  saved → {path}")


def style_bar(ax, title, xlabel="", ylabel="Count"):
    ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))


# ── charts ────────────────────────────────────────────────────────────────────

def chart_messages_over_time(messages, out_dir):
    """Daily message volume across the full corpus."""
    ts = messages.set_index("timestamp").resample("D")["id"].count().rename("count")
    if ts.empty:
        return

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.fill_between(ts.index, ts.values, alpha=0.35)
    ax.plot(ts.index, ts.values, linewidth=1.2)
    style_bar(ax, "Daily message volume", ylabel="Messages / day")
    ax.xaxis.set_major_locator(matplotlib.dates.AutoDateLocator())
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %d"))
    fig.autofmt_xdate()
    savefig(fig, out_dir, "01_messages_over_time.png")


def chart_top_locations(joined, out_dir, top_n=25):
    counts = joined.groupby("name_en")["message_id"].nunique().nlargest(top_n)
    if counts.empty:
        return

    fig, ax = plt.subplots(figsize=(10, max(4, len(counts) * 0.35)))
    counts[::-1].plot.barh(ax=ax, color="darkorange")
    style_bar(ax, f"Top {top_n} locations by unique messages", ylabel="Location")
    savefig(fig, out_dir, "02_top_locations.png")


def chart_locations_per_front(joined, out_dir):
    if joined["front"].isna().all():
        return
    counts = joined.groupby("front")["message_id"].nunique().sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(8, 4))
    counts.plot.bar(ax=ax, color="mediumseagreen", rot=30)
    style_bar(ax, "Unique messages mentioning each front")
    savefig(fig, out_dir, "03_messages_by_front.png")


def chart_hourly_activity(joined, out_dir):
    counts = joined.groupby("hour")["message_id"].nunique()
    counts = counts.reindex(range(24), fill_value=0)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(counts.index, counts.values, color="slateblue", width=0.7)
    style_bar(ax, "Activity by hour of day (UTC)", xlabel="Hour (0–23)")
    ax.set_xticks(range(24))
    savefig(fig, out_dir, "04_hourly_activity.png")


def chart_day_of_week(joined, out_dir):
    counts = joined.groupby("dow")["message_id"].nunique()
    counts = counts.reindex(DAYS_ORDER, fill_value=0)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(counts.index, counts.values, color="tomato", width=0.6)
    style_bar(ax, "Activity by day of week", xlabel="Day")
    savefig(fig, out_dir, "05_day_of_week.png")


def chart_front_over_time(joined, out_dir):
    if joined["front"].isna().all():
        return
    daily = (
        joined.dropna(subset=["front"])
        .groupby(["date", "front"])["message_id"]
        .nunique()
        .reset_index()
    )
    daily["date"] = pd.to_datetime(daily["date"])
    fronts = daily["front"].unique()

    fig, ax = plt.subplots(figsize=(12, 5))
    for front in sorted(fronts):
        sub = daily[daily["front"] == front].set_index("date")["message_id"]
        sub = sub.resample("W").sum()
        ax.plot(sub.index, sub.values, marker="o", markersize=3, label=front)

    style_bar(ax, "Weekly messages per front over time", ylabel="Messages / week")
    ax.legend(fontsize=8)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %d"))
    fig.autofmt_xdate()
    savefig(fig, out_dir, "06_front_over_time.png")


def chart_top_locations_per_front(joined, out_dir, top_n=12):
    """Small-multiples: top locations within each front."""
    if joined["front"].isna().all():
        return
    fronts = sorted(joined["front"].dropna().unique())
    if not fronts:
        return

    ncols = min(2, len(fronts))
    nrows = (len(fronts) + ncols - 1) // ncols
    row_h = max(4, top_n * 0.42)
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 7, nrows * row_h))
    axes = [axes] if len(fronts) == 1 else list(
        axes.flat if hasattr(axes, "flat") else axes
    )

    for ax, front in zip(axes, fronts):
        sub = joined[joined["front"] == front]
        counts = sub.groupby("name_en")["message_id"].nunique().nlargest(top_n)
        counts[::-1].plot.barh(ax=ax, color="darkorange")
        style_bar(ax, f"Top locations — {front}", ylabel="")
        ax.tick_params(axis="y", labelsize=8)

    for ax in axes[len(fronts):]:
        ax.set_visible(False)

    fig.suptitle(f"Top {top_n} locations per front", fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()
    savefig(fig, out_dir, "07_top_locations_per_front.png")


def chart_hourly_activity_per_front(joined, out_dir):
    """Line chart: hour-of-day activity broken down by front."""
    if joined["front"].isna().all():
        return
    sub = joined.dropna(subset=["front"])
    pivot = (
        sub.groupby(["hour", "front"])["message_id"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(range(24), fill_value=0)
    )

    fig, ax = plt.subplots(figsize=(11, 5))
    for front in sorted(pivot.columns):
        ax.plot(pivot.index, pivot[front], marker="o", markersize=4, label=front)

    style_bar(ax, "Hourly activity by front (UTC)", xlabel="Hour (0–23)")
    ax.set_xticks(range(24))
    ax.legend(fontsize=9)
    savefig(fig, out_dir, "08_hourly_activity_per_front.png")


def chart_dow_per_front(joined, out_dir):
    """Grouped bar: day-of-week activity per front."""
    if joined["front"].isna().all():
        return
    sub = joined.dropna(subset=["front"])
    pivot = (
        sub.groupby(["dow", "front"])["message_id"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(DAYS_ORDER, fill_value=0)
    )

    fig, ax = plt.subplots(figsize=(10, 5))
    pivot.plot.bar(ax=ax, rot=30, width=0.75)
    style_bar(ax, "Day-of-week activity by front", xlabel="Day")
    ax.legend(fontsize=9, title="Front")
    savefig(fig, out_dir, "09_dow_per_front.png")


def chart_location_correlation(joined, out_dir, top_n=40):
    """Pearson correlation matrix of top N locations (binary presence per message)."""
    top_locs = (
        joined.groupby("name_en")["message_id"].nunique()
        .nlargest(top_n).index.tolist()
    )
    sub = joined[joined["name_en"].isin(top_locs)]

    # binary message × location matrix
    binary = (
        sub.pivot_table(index="message_id", columns="name_en", aggfunc="size", fill_value=0)
        .clip(upper=1)
        .reindex(columns=top_locs, fill_value=0)
    )
    if binary.shape[1] < 2:
        return

    corr = binary.corr()
    n = len(corr)
    cell = max(0.35, 12 / n)
    fig, ax = plt.subplots(figsize=(n * cell + 1.5, n * cell + 1.5))

    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    plt.colorbar(im, ax=ax, fraction=0.03, pad=0.02, label="Pearson r")

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(corr.columns, rotation=90, fontsize=max(5, 9 - n // 10))
    ax.set_yticklabels(corr.index, fontsize=max(5, 9 - n // 10))
    ax.set_title(
        f"Location co-mention correlation matrix (top {n})",
        fontsize=13, fontweight="bold", pad=10,
    )
    fig.tight_layout()
    savefig(fig, out_dir, "11_location_correlation.png")


def chart_location_cooccurrence(joined, out_dir, top_n=20):
    """Which locations appear together most often in the same message?"""
    pairs = Counter()
    for msg_id, grp in joined.groupby("message_id")["name_en"]:
        locs = list(grp.unique())
        if len(locs) > 1:
            for a, b in combinations(sorted(locs), 2):
                pairs[(a, b)] += 1

    if not pairs:
        return

    top_pairs = pairs.most_common(top_n)
    labels = [f"{a}  ×  {b}" for (a, b), _ in top_pairs]
    values = [c for _, c in top_pairs]

    fig, ax = plt.subplots(figsize=(10, max(4, len(labels) * 0.35)))
    ax.barh(labels[::-1], values[::-1], color="mediumpurple")
    style_bar(ax, f"Top {top_n} location co-occurrences\n(same message)", ylabel="Location pair")
    savefig(fig, out_dir, "10_location_cooccurrence.png")


# ── summary printout ──────────────────────────────────────────────────────────

def print_summary(messages, locations, msg_loc, joined):
    n_msg          = len(messages)
    n_with_loc     = joined["message_id"].nunique()
    n_locations    = len(locations)
    n_used_locs    = joined["location_id"].nunique()
    n_channels     = messages["channel"].nunique()
    date_range     = f"{messages['timestamp'].min():%Y-%m-%d}  →  {messages['timestamp'].max():%Y-%m-%d}"

    print()
    print("=" * 56)
    print("  DATASET SUMMARY")
    print("=" * 56)
    print(f"  Total messages          : {n_msg:,}")
    print(f"  Messages with locations : {n_with_loc:,}  ({100*n_with_loc/max(n_msg,1):.1f}%)")
    print(f"  Unique locations (DB)   : {n_locations:,}")
    print(f"  Locations cited         : {n_used_locs:,}")
    print(f"  Channels                : {n_channels:,}")
    print(f"  Date range              : {date_range}")
    print()
    print("  Top 10 locations by unique messages:")
    top10 = joined.groupby("name_en")["message_id"].nunique().nlargest(10)
    for name, cnt in top10.items():
        print(f"    {cnt:>5}  {name}")
    print()
    if not joined["front"].isna().all():
        print("  Messages by front:")
        by_front = joined.groupby("front")["message_id"].nunique().sort_values(ascending=False)
        for front, cnt in by_front.items():
            print(f"    {cnt:>5}  {front}")
        print()
        print("  Top 5 locations per front:")
        for front in sorted(joined["front"].dropna().unique()):
            sub = joined[joined["front"] == front]
            top5 = sub.groupby("name_en")["message_id"].nunique().nlargest(5)
            print(f"    [{front}]")
            for name, cnt in top5.items():
                print(f"      {cnt:>5}  {name}")
        print()
    print("=" * 56)
    print()


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EDA for geo-tagged Telegram messages")
    parser.add_argument("--out-dir", default="scrap/charts",
                        help="Directory to save chart PNGs (default: scrap/charts)")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    print("Loading data ...", flush=True)
    messages, locations, msg_loc = load_data()

    if messages.empty:
        print("No messages found. Run the scraper first.")
        sys.exit(1)

    joined = build_joined(messages, locations, msg_loc)

    if joined.empty:
        print("No messages have locations assigned yet. Run the processor first.")
        sys.exit(1)

    print_summary(messages, locations, msg_loc, joined)

    print("Generating charts ...")
    chart_messages_over_time(messages, out_dir=args.out_dir)
    chart_top_locations(joined, out_dir=args.out_dir)
    chart_locations_per_front(joined, out_dir=args.out_dir)
    chart_hourly_activity(joined, out_dir=args.out_dir)
    chart_day_of_week(joined, out_dir=args.out_dir)
    chart_front_over_time(joined, out_dir=args.out_dir)
    chart_top_locations_per_front(joined, out_dir=args.out_dir)
    chart_hourly_activity_per_front(joined, out_dir=args.out_dir)
    chart_dow_per_front(joined, out_dir=args.out_dir)
    chart_location_correlation(joined, out_dir=args.out_dir)
    chart_location_cooccurrence(joined, out_dir=args.out_dir)

    print(f"\nDone. {len(os.listdir(args.out_dir))} files in {args.out_dir}/")


if __name__ == "__main__":
    main()
