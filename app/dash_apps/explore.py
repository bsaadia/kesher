"""Interactive exploratory dashboard, embedded into the Flask server via Dash.

Mounts at ``/``, the app's main route. Provides a point map of where messages are
located (click a marker to inspect its messages), plus front-comparison and
facet views driven by a shared date-range picker and time-granularity
toggle. Built to be extended with further exploratory views.
"""

import math

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, dcc, html, Input, Output, Patch
from dash.exceptions import PreventUpdate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from models.base import engine
from models.message import Message
from models.location import Location
from models.activity import Activity
from models.associations import MessageLocation, MessageActivity

# Own session factory so the dashboard stays decoupled from the request-scoped
# g.db_session lifecycle in app/__init__.py.
Session = sessionmaker(bind=engine)

URL_BASE = "/"

# Raw `Message.channel` values (numeric Telegram channel ids, as stored by
# the scraper) mapped to a display name for the messages sidebar; channels
# with no entry show the raw id.
_CHANNEL_DISPLAY_NAMES = {"-1001155294424": "צה״ל - הערוץ הרשמי"}

# pandas resample frequency aliases keyed by the granularity control's value.
# Month-end alias was renamed "M" -> "ME" in pandas 2.2.
_MONTH = "ME" if tuple(map(int, pd.__version__.split(".")[:2])) >= (2, 2) else "M"
FREQ = {"day": "D", "week": "W", "month": _MONTH}

# Empty-state figure so callbacks always return a valid figure.
_EMPTY_FIG = px.line(template="plotly_white").update_layout(
    annotations=[dict(text="No messages in range", showarrow=False,
                      font=dict(size=16, color="#888"))]
)

# Roughly centers the Israel/Gaza/Lebanon/Syria area covered by the gazetteer.
_MAP_CENTER = {"lat": 31.5, "lon": 35.0}

# scatter_mapbox (not the newer scatter_map/MapLibre variant) — the Plotly.js
# bundled with this Dash version only understands the "scattermapbox" trace
# type, so scatter_map's "scattermap" traces silently fail to render.
_EMPTY_MAP_FIG = px.scatter_mapbox(
    pd.DataFrame({"lat": [_MAP_CENTER["lat"]], "lon": [_MAP_CENTER["lon"]]}),
    lat="lat", lon="lon", zoom=5, center=_MAP_CENTER,
    template="plotly_white", mapbox_style="carto-positron",
)
_EMPTY_MAP_FIG.data = ()  # keep the basemap frame, drop the seed point
_EMPTY_MAP_FIG.update_layout(
    margin=dict(l=0, r=0, t=0, b=0),
    annotations=[dict(text="No messages in range", showarrow=False,
                      xref="paper", yref="paper", x=0.5, y=0.5,
                      font=dict(size=16, color="#333"))],
)


def load_data(group_by: str) -> pd.DataFrame:
    """One row per (message, <group_by>) pair; the group column is NaN when
    a message has no matching tag (untagged messages are dropped downstream,
    when filtering). Columns: id, timestamp, <group_by>.

    ``group_by`` is "front" (via the location gazetteer) or "activity" (via
    the AIR/GROUND/PROJECTILE/CASUALTIES classification) — both are optional,
    possibly-multiple-per-message tags, so they're queried and handled the
    same way.
    """
    if group_by == "activity":
        query = (
            select(Message.id, Message.timestamp, Activity.category.label("activity"))
            .outerjoin(MessageActivity, Message.id == MessageActivity.message_id)
            .outerjoin(Activity, MessageActivity.activity_id == Activity.id)
        )
    else:  # front
        query = (
            select(Message.id, Message.timestamp, Location.front)
            .outerjoin(MessageLocation, Message.id == MessageLocation.message_id)
            .outerjoin(Location, MessageLocation.location_id == Location.id)
        )
    with Session() as session:
        rows = session.execute(query).all()

    df = pd.DataFrame(rows, columns=["id", "timestamp", group_by])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.dropna(subset=["timestamp"])


def _build_color_map(values) -> dict:
    """Assign each value a fixed color from a repeating palette, keyed by
    sorted value so the mapping is stable regardless of which subset of
    values is present in any given filtered view."""
    from itertools import cycle
    return dict(zip(sorted(values), cycle(px.colors.qualitative.Plotly)))


def _order_by_count(df: pd.DataFrame, group_col: str, id_col: str = "id") -> list:
    """Category values ordered by descending distinct-message count (over
    the full, unfiltered dataset) — used everywhere a chart needs a stable
    front/activity order, instead of alphabetical."""
    counts = df.dropna(subset=[group_col]).groupby(group_col)[id_col].nunique()
    return counts.sort_values(ascending=False).index.tolist()


def _filter_window(df: pd.DataFrame, start, end, group_by) -> pd.DataFrame:
    """Filter to the selected date window and drop rows missing the group tag."""
    mask = (df["timestamp"] >= pd.Timestamp(start)) & \
           (df["timestamp"] <= pd.Timestamp(end) + pd.Timedelta(days=1))
    return df.loc[mask].dropna(subset=[group_by])



def load_location_data() -> pd.DataFrame:
    """One row per (message, location, activity) combination — a message can
    have multiple locations and/or multiple activity tags, so both fan out
    independently. ``activity`` is NaN when the message has no activity
    classification. Columns: message_id, timestamp, location_id, name_en,
    name_he, name_ar, front, lat, lon, activity."""
    query = (
        select(Message.id, Message.timestamp, Location.id.label("location_id"),
               Location.name_en, Location.name_he, Location.name_ar, Location.front,
               Location.lat, Location.lon, Activity.category.label("activity"))
        .join(MessageLocation, Message.id == MessageLocation.message_id)
        .join(Location, MessageLocation.location_id == Location.id)
        .outerjoin(MessageActivity, Message.id == MessageActivity.message_id)
        .outerjoin(Activity, MessageActivity.activity_id == Activity.id)
    )
    with Session() as session:
        rows = session.execute(query).all()

    df = pd.DataFrame(rows, columns=["message_id", "timestamp", "location_id",
                                      "name_en", "name_he", "name_ar", "front", "lat", "lon", "activity"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.dropna(subset=["timestamp"])


def load_messages_for_location(location_id: int) -> pd.DataFrame:
    """Full message text for one location, most recent first — for the
    map's click-to-inspect sidebar."""
    query = (
        select(Message.id, Message.timestamp, Message.text, Message.channel)
        .join(MessageLocation, Message.id == MessageLocation.message_id)
        .where(MessageLocation.location_id == location_id)
        .order_by(Message.timestamp.desc())
    )
    with Session() as session:
        rows = session.execute(query).all()

    df = pd.DataFrame(rows, columns=["id", "timestamp", "text", "channel"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def build_location_messages_panel(location_name: str, messages_df: pd.DataFrame):
    """Render one location's messages as visually separated cards (bordered,
    alternating background) so consecutive messages don't blur together.
    ``messages_df`` is expected most-recent-first (as returned by
    ``load_messages_for_location``); order is preserved, not re-sorted."""
    header = html.H3(f"{location_name} ({len(messages_df)} messages)",
                      style={"fontSize": "1rem", "margin": "0 0 0.75rem"})

    if messages_df.empty:
        return [header, html.P("No messages found for this location.",
                                style={"color": "#888", "fontSize": "0.85rem"})]

    cards = []
    for i, row in enumerate(messages_df.itertuples()):
        cards.append(html.Div(
            [
                html.Div([
                    html.Span(row.timestamp.strftime("%d %b %Y, %H:%M"),
                              style={"fontWeight": "600", "fontSize": "0.8rem"}),
                    html.Span(f"  ·  {_CHANNEL_DISPLAY_NAMES.get(row.channel, row.channel)}",
                              style={"color": "#888", "fontSize": "0.75rem"}),
                ], style={"marginBottom": "0.4rem"}),
                html.Div(row.text, dir="auto",
                         style={"whiteSpace": "pre-wrap", "fontSize": "0.9rem", "lineHeight": "1.4"}),
            ],
            style={
                "padding": "0.75rem 0.9rem",
                "marginBottom": "0.75rem",
                "backgroundColor": "#f4f4f4" if i % 2 == 0 else "#ffffff",
                "border": "1px solid #ddd",
                "borderRadius": "8px",
            },
        ))
    return [header] + cards


def build_comparison_figure(msg_df: pd.DataFrame, loc_df: pd.DataFrame,
                             granularity, fronts, color_map):
    """Three-part, time-synced comparison across all fronts, over the full
    history — the date-range picker/slider no longer re-filter this data,
    they just pick which part of the (always fully plotted) x-axis is
    visible, via the graph's own zoom/pan:
    1. stacked messages per front
    2. stacked distinct locations mentioned per front
    3. a front x period heatmap (period set by ``granularity``, same as the
       two bar charts above) of the messages-per-location ratio, with a thin
       vertical line overlaid on each cell whose height encodes the raw
       message count.

    ``fronts`` is the full, fixed list of known fronts (not just whichever
    happen to have data at all), so the row layout stays stable.
    """
    msg_df = msg_df.dropna(subset=["front"])
    loc_df = loc_df.dropna(subset=["front"])
    if msg_df.empty and loc_df.empty:
        return _EMPTY_FIG

    # Distinct message id, not row count: msg_df has one row per (message,
    # location) pair, so a message mentioning two same-front locations would
    # otherwise be double-counted for that front.
    msg_counts = (
        msg_df.groupby([pd.Grouper(key="timestamp", freq=FREQ[granularity]), "front"])["id"]
        .nunique()
        .reset_index(name="messages")
    )
    loc_counts = (
        loc_df.groupby([pd.Grouper(key="timestamp", freq=FREQ[granularity]), "front"])["location_id"]
        .nunique()
        .reset_index(name="locations")
    )

    # Heatmap now shares the same granularity control as the two bar charts
    # above (previously pinned to week resolution) — front x period is the
    # requested grain, whatever period that is.
    periodic = msg_counts.merge(loc_counts, on=["timestamp", "front"], how="outer")
    periodic["messages"] = periodic["messages"].fillna(0)
    periodic["locations"] = periodic["locations"].fillna(0)
    periodic["ratio"] = periodic["messages"] / periodic["locations"].replace(0, pd.NA)

    periods = sorted(periodic["timestamp"].unique())
    ratio_matrix = periodic.pivot(index="front", columns="timestamp", values="ratio").reindex(
        index=fronts, columns=periods)
    msg_matrix = periodic.pivot(index="front", columns="timestamp", values="messages").reindex(
        index=fronts, columns=periods)

    n = len(fronts)
    heatmap_weight = max(0.4, min(0.6, n * 0.07))
    bar_weight = (1 - heatmap_weight) / 2
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
        row_heights=[bar_weight, bar_weight, heatmap_weight],
        subplot_titles=["Messages per front", "Distinct locations per front",
                        "Messages-per-location ratio (line height = message count)"],
    )

    for front in fronts:
        sub = msg_counts[msg_counts["front"] == front]
        fig.add_bar(x=sub["timestamp"], y=sub["messages"], name=front,
                    marker_color=color_map.get(front), legendgroup=front,
                    showlegend=True, row=1, col=1)

    for front in fronts:
        sub = loc_counts[loc_counts["front"] == front]
        fig.add_bar(x=sub["timestamp"], y=sub["locations"], name=front,
                    marker_color=color_map.get(front), legendgroup=front,
                    showlegend=False, row=2, col=1)

    # Numeric row positions (rather than the front names directly) so the
    # message-count overlay below can offset above/below each row's center —
    # a category axis has no notion of a fractional position between ticks.
    front_positions = list(range(n))

    period_label = {"day": "", "week": "week of ", "month": "month of "}.get(granularity, "")
    date_fmt = "%b %Y" if granularity == "month" else "%d %b %Y"
    fig.add_trace(go.Heatmap(
        z=ratio_matrix.values, x=periods, y=front_positions,
        customdata=np.dstack([msg_matrix.values, np.tile(fronts, (len(periods), 1)).T]),
        colorscale="YlOrRd", colorbar=dict(title="Ratio", len=heatmap_weight, y=heatmap_weight / 2),
        hovertemplate=f"%{{customdata[1]}} — {period_label}%{{x|{date_fmt}}}<br>Ratio: %{{z:.1f}}<br>"
                      "Messages: %{customdata[0]:.0f}<extra></extra>",
    ), row=3, col=1)
    fig.update_yaxes(tickmode="array", tickvals=front_positions, ticktext=fronts,
                      title_text="Front", row=3, col=1)

    # Message count encoded as a thin vertical line centered on each cell,
    # height scaled (sqrt, for perceptual fairness) and capped so it can't
    # touch the neighboring row. One trace for the whole grid, using a None
    # after each segment to keep the lines disconnected from one another.
    max_messages = periodic["messages"].max() or 1
    line_x, line_y = [], []
    for i, front in enumerate(fronts):
        counts = msg_matrix.loc[front].fillna(0)
        half_heights = 0.45 * (counts / max_messages) ** 0.5
        for period, half_height in zip(periods, half_heights):
            line_x += [period, period, None]
            line_y += [i - half_height, i + half_height, None]
    fig.add_scatter(x=line_x, y=line_y, mode="lines", line=dict(color="black", width=1.5),
                     showlegend=False, hoverinfo="skip", row=3, col=1)

    # fixedrange on every y-axis: box-drag zoom is horizontal-only (the time
    # axis is the only one meant to be zoomed; a locked y keeps drag-zoom
    # from also rescaling the bars/heatmap vertically).
    fig.update_yaxes(title_text="Messages", fixedrange=True, row=1, col=1)
    fig.update_yaxes(title_text="Locations", fixedrange=True, row=2, col=1)
    fig.update_yaxes(title_text="Front", fixedrange=True, row=3, col=1)
    fig.update_layout(
        barmode="stack",
        template="plotly_white",
        height=max(700, 250 + 250 + n * 60),
        margin=dict(l=100, r=20, t=50, b=40),
        legend_title_text="Front",
    )
    return fig


def build_front_facet_figure(msg_df: pd.DataFrame, loc_df: pd.DataFrame, start, end,
                              granularity, fronts: list):
    """One (locations, messages) scatter subplot per front, filtered to the
    selected date window and bucketed at the chosen granularity. Each dot is
    one period; color encodes time (a continuous scale shared across all
    subplots, no colorbar — the color dimension is just for relative
    ordering within a panel, not something worth a legend) so the whole
    history is visible at once, rather than animating through it frame by
    frame. x/y axis ranges are fixed to the same span on every subplot (not
    auto-scaled per front) so bubble positions are directly comparable
    across fronts."""
    msg_df = _filter_window(msg_df, start, end, "front")
    loc_df = _filter_window(loc_df, start, end, "front")
    if msg_df.empty and loc_df.empty:
        return _EMPTY_FIG

    # Distinct message id, not row count: msg_df has one row per (message,
    # location) pair, so a message mentioning two same-front locations would
    # otherwise be double-counted for that front.
    msg_counts = (
        msg_df.groupby([pd.Grouper(key="timestamp", freq=FREQ[granularity]), "front"])["id"]
        .nunique()
        .reset_index(name="messages")
    )
    loc_counts = (
        loc_df.groupby([pd.Grouper(key="timestamp", freq=FREQ[granularity]), "front"])["location_id"]
        .nunique()
        .reset_index(name="locations")
    )
    points = msg_counts.merge(loc_counts, on=["timestamp", "front"], how="outer")
    points["messages"] = points["messages"].fillna(0)
    points["locations"] = points["locations"].fillna(0)
    points = points[(points["messages"] > 0) | (points["locations"] > 0)]
    if points.empty:
        return _EMPTY_FIG

    period_label = {"day": "", "week": "week of ", "month": "month of "}.get(granularity, "")
    date_fmt = "%b %Y" if granularity == "month" else "%d %b %Y"
    points["period_of"] = points["timestamp"].dt.strftime(date_fmt)
    points["time_value"] = points["timestamp"].map(pd.Timestamp.toordinal)

    cols = 3
    rows = -(-len(fronts) // cols)  # ceil division
    fig = make_subplots(rows=rows, cols=cols, subplot_titles=fronts,
                         horizontal_spacing=0.06, vertical_spacing=0.12)

    for i, front in enumerate(fronts):
        sub = points[points["front"] == front]
        row, col = i // cols + 1, i % cols + 1
        fig.add_trace(go.Scatter(
            x=sub["locations"], y=sub["messages"], mode="markers", name=front,
            marker=dict(size=9, color=sub["time_value"], coloraxis="coloraxis"),
            customdata=sub[["period_of"]].to_numpy(),
            hovertemplate=f"<b>{front}</b><br>{period_label}" + "%{customdata[0]}<br>"
                          "Distinct locations: %{x}<br>Messages: %{y}<extra></extra>",
            showlegend=False,
        ), row=row, col=col)
        if row != 1:  # top row's label would just repeat for every row below it
            fig.update_xaxes(title_text="Distinct locations", row=row, col=col)
        fig.update_yaxes(title_text="Messages", row=row, col=col)

    # Same range on every subplot (with a little headroom) rather than each
    # front auto-scaling to its own data.
    x_pad, y_pad = points["locations"].max() * 0.05 or 1, points["messages"].max() * 0.05 or 1
    fig.update_xaxes(range=[-x_pad, points["locations"].max() + x_pad])
    fig.update_yaxes(range=[-y_pad, points["messages"].max() + y_pad])

    fig.update_layout(
        template="plotly_white",
        height=280 * rows,
        margin=dict(l=60, r=20, t=50, b=40),
        coloraxis=dict(colorscale="Viridis", reversescale=True, showscale=False),
    )
    return fig


def _bounds_zoom_center(lats, lons, width_px=900, height_px=650):
    """Zoom level and center that fit a set of lat/lon points in a mapbox
    view of the given pixel size. Standard web-mercator bounds-to-zoom
    formula (the same one Plotly's own hexbin figure factory uses)."""
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    center = {"lat": (lat_min + lat_max) / 2, "lon": (lon_min + lon_max) / 2}

    world_px = 256

    def lat_rad(lat):
        s = math.sin(lat * math.pi / 180)
        return math.log((1 + s) / (1 - s)) / 2

    def zoom_for(map_px, fraction):
        return math.log(map_px / world_px / fraction, 2) if fraction else 21

    lat_fraction = (lat_rad(lat_max) - lat_rad(lat_min)) / math.pi
    lon_fraction = ((lon_max - lon_min) % 360) / 360

    zoom = min(zoom_for(height_px, lat_fraction), zoom_for(width_px, lon_fraction), 21)
    return zoom - 0.3, center  # small margin so edge points aren't clipped


def build_map_figure(df: pd.DataFrame):
    """Static point map: one marker per location, colored by total distinct
    message count summed across the whole history (previously a hexbin
    density). Counts distinct ``message_id`` rather than raw row count —
    ``df`` has one row per (message, location, activity) combination, so a
    message tagged with two activities would otherwise be counted twice."""
    if df.empty:
        return _EMPTY_MAP_FIG

    location_counts = df.groupby(["location_id", "name_en", "name_he", "name_ar", "lat", "lon"],
                                  dropna=False)["message_id"] \
        .nunique().reset_index(name="messages")
    if location_counts.empty:
        return _EMPTY_MAP_FIG

    # Ascending, so busier locations are drawn last within the trace and
    # sit on top of quieter, overlapping neighbors rather than being buried.
    location_counts = location_counts.sort_values("messages")

    # A handful of locations (e.g. Gaza City) have message counts far above
    # the rest, which washes out the color scale for everywhere else if the
    # color range spans the true max. Clip the color range at the 95th
    # percentile — the few busiest locations saturate to the top color, but
    # the bulk of (lower-volume) locations get the full color range and
    # become distinguishable from each other. Hover text still shows the
    # true, unclipped count.
    color_cap = max(location_counts["messages"].quantile(0.95), location_counts["messages"].min() + 1)

    zoom, center = _bounds_zoom_center(location_counts["lat"], location_counts["lon"])

    fig = px.scatter_mapbox(
        location_counts, lat="lat", lon="lon", color="messages",
        color_continuous_scale="YlOrRd",
        range_color=[0, color_cap],
        hover_name="name_he",
        hover_data={"name_en": True, "name_ar": True, "messages": True, "lat": False, "lon": False},
        custom_data=["location_id"],
        zoom=zoom, center=center,
        template="plotly_white", mapbox_style="carto-positron",
    )
    fig.update_traces(marker=dict(size=12))

    # Scattermapbox markers have no `marker.line` outline support, so fake one
    # with a slightly larger black-marker trace drawn underneath the colored
    # points (added first so it renders behind, not on click-hoverable on top).
    outline = go.Scattermapbox(
        lat=location_counts["lat"], lon=location_counts["lon"],
        mode="markers", marker=dict(size=15, color="black"),
        hoverinfo="skip", showlegend=False,
    )
    fig.add_trace(outline)
    fig.data = (fig.data[-1],) + fig.data[:-1]

    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
    fig.update_coloraxes(showscale=False)
    return fig


def _days_between(start, end) -> int:
    return (pd.Timestamp(end).normalize() - pd.Timestamp(start).normalize()).days


def _day_offset_to_date(base, offset: int) -> str:
    return (pd.Timestamp(base).normalize() + pd.Timedelta(days=offset)).date().isoformat()


def _build_day_marks(min_date, max_date) -> dict:
    """Quarterly tick marks (as day-offsets from min_date) for a day-resolution
    slider spanning a multi-year range. No mark is forced onto the last day —
    it would sit right on top of (and overlap) the nearest quarterly tick."""
    min_date, max_date = pd.Timestamp(min_date).normalize(), pd.Timestamp(max_date).normalize()
    quarters = pd.date_range(min_date, max_date, freq="QS")
    marks = {int((q - min_date).days): q.strftime("%b '%y") for q in quarters}
    marks[0] = min_date.strftime("%b '%y")
    return marks


def init_explore_dash(server):
    """Attach the exploratory Dash app to an existing Flask ``server``."""
    dash_app = Dash(
        server=server,
        url_base_pathname=URL_BASE,
        title="Explore — Tzahal Mapper",
    )

    # Load once to seed the date-picker bounds; callbacks reload live so new
    # messages from the pipeline show up on refresh. Outer joins mean every
    # message is present in both seeds regardless of tagging, so either can
    # supply the overall date bounds.
    seed_front = load_data("front")
    if seed_front.empty:
        min_date = max_date = pd.Timestamp.today().normalize()
    else:
        min_date, max_date = seed_front["timestamp"].min(), seed_front["timestamp"].max()

    total_days = max(_days_between(min_date, max_date), 1)  # RangeSlider needs min < max
    day_marks = _build_day_marks(min_date, max_date)

    # Fixed once from the full (unfiltered) dataset so a group's color never
    # shifts depending on which subset the current date range happens to show.
    front_color_map = _build_color_map(seed_front["front"].dropna().unique())

    # Every chart's front order — by descending total message count, not
    # alphabetical — fixed once so a front's rank stays stable across views
    # (and doesn't reshuffle as a filtered subset changes).
    front_order = _order_by_count(seed_front, "front")

    # Built once at boot: the map is a static full-history density with no
    # controls driving it. The comparison/facet figures below are also seeded
    # here (from the same data, at the controls' default values) so the page
    # renders populated on first load without needing their callbacks to
    # fire — those callbacks (prevent_initial_call=True) only run in
    # response to actual user interaction from then on.
    loc_data = load_location_data()
    map_figure = build_map_figure(loc_data)
    comparison_figure = build_comparison_figure(seed_front, loc_data, "week", front_order, front_color_map)
    front_facet_figure = build_front_facet_figure(seed_front, loc_data, min_date.date(), max_date.date(),
                                                   "week", front_order)

    dash_app.layout = html.Div(
        style={"font-family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
               "padding": "1.5rem", "maxWidth": "1200px", "margin": "0 auto"},
        children=[
            html.Div(
                style={"display": "flex", "justifyContent": "space-between",
                       "alignItems": "flex-start"},
                children=[
                    html.H1("Explore message activity", style={"fontSize": "1.4rem", "margin": "0"}),
                    html.Div(className="info-icon-wrapper", children=[
                        html.Div("i", className="info-icon"),
                        html.Div(className="info-popover", children=[
                            html.P(
                                [
                                    "Placeholder about text: this dashboard tracks messages from public "
                                    "Telegram channels and tags them by location and activity type. "
                                    "Figures update as new data is scraped and processed. ",
                                    html.A("Read more about our methodology", href="/methodology"),
                                    ".",
                                ],
                                style={"margin": "0"},
                            ),
                        ]),
                    ]),
                ],
            ),

            html.H2("Where messages are located", style={"fontSize": "1.2rem", "margin": "1.25rem 0 0.5rem"}),
            html.P("One marker per location, colored by total message count across the whole history. "
                   "Click a marker to see its messages.",
                   style={"fontSize": "0.85rem", "color": "#888", "margin": "0.5rem 0 1rem"}),
            html.Div(
                style={"display": "flex", "gap": "1.25rem", "alignItems": "flex-start"},
                children=[
                    dcc.Graph(id="map-graph", figure=map_figure,
                              style={"height": "650px", "flex": "2", "minWidth": "0"},
                              config={"scrollZoom": True}),
                    dcc.Loading(
                        type="circle",
                        parent_style={"flex": "1", "minWidth": "280px", "maxWidth": "380px"},
                        children=html.Div(
                            id="location-messages-panel",
                            children=html.P("Click a marker to see messages for that location.",
                                             style={"color": "#888", "fontSize": "0.85rem"}),
                            style={"height": "650px", "overflowY": "auto",
                                   "border": "1px solid #ddd", "borderRadius": "8px",
                                   "padding": "1rem"},
                        ),
                    ),
                ],
            ),

            html.Hr(style={"borderColor": "#333", "margin": "2.5rem 0 1.5rem"}),
            html.H2("Front comparison", style={"fontSize": "1.2rem"}),
            html.P("Messages, distinct locations, and the messages-per-location ratio for every "
                   "front, all on the same time axis — the time frame above and the slider below "
                   "both drive (and follow) zooming/panning on the chart.",
                   style={"fontSize": "0.85rem", "color": "#888", "margin": "0.5rem 0 1rem"}),

            # Sticky once scrolled past the map above (its normal in-flow spot
            # is right here); scrolling back up past that spot un-sticks it,
            # so it only overlays content once the map itself is out of view.
            html.Div(
                style={"position": "sticky", "top": "0", "zIndex": "10",
                       "backgroundColor": "#fff", "paddingTop": "0.5rem",
                       "paddingBottom": "0.75rem", "borderBottom": "1px solid #eee"},
                children=[
                    html.Div(
                        style={"display": "flex", "gap": "2rem", "flexWrap": "wrap",
                               "alignItems": "center", "margin": "0 0 0.5rem"},
                        children=[
                            html.Div([
                                html.Label("Time frame", style={"display": "block",
                                                                "fontSize": "0.8rem", "color": "#888"}),
                                html.Div(
                                    style={"display": "flex", "gap": "0.5rem", "alignItems": "center"},
                                    children=[
                                        dcc.DatePickerRange(
                                            id="date-range",
                                            min_date_allowed=min_date.date(),
                                            max_date_allowed=max_date.date(),
                                            start_date=min_date.date(),
                                            end_date=max_date.date(),
                                            display_format="D MMM YYYY",
                                        ),
                                        html.Button("Reset", id="reset-date-range",
                                                    style={"fontSize": "0.8rem", "padding": "0.35rem 0.6rem"}),
                                    ],
                                ),
                            ]),
                            html.Div([
                                html.Label("Granularity", style={"display": "block",
                                                                 "fontSize": "0.8rem", "color": "#888"}),
                                dcc.RadioItems(
                                    id="granularity",
                                    options=[{"label": g.title(), "value": g}
                                             for g in ("day", "week", "month")],
                                    value="week",
                                    inline=True,
                                    labelStyle={"marginRight": "0.75rem"},
                                ),
                            ]),
                        ],
                    ),
                    dcc.RangeSlider(
                        id="time-slider",
                        min=0, max=total_days,
                        value=[0, total_days],
                        marks=day_marks,
                        step=1,
                        allowCross=False,
                    ),
                ],
            ),
            dcc.Graph(id="comparison-graph", figure=comparison_figure),

            html.Hr(style={"borderColor": "#333", "margin": "2.5rem 0 1.5rem"}),
            html.H2("Messages vs. locations per front-period", style={"fontSize": "1.2rem"}),
            html.P("Each dot is one period (day/week/month, per the granularity control above) "
                   "for that front within the selected time frame; color marks when it occurred. "
                   "Axes are fixed to the same scale across fronts for direct comparison.",
                   style={"fontSize": "0.85rem", "color": "#888", "margin": "0.5rem 0 1rem"}),
            dcc.Graph(id="front-facet-scatter", figure=front_facet_figure),

            html.Footer(
                style={"marginTop": "3rem", "paddingTop": "1rem", "borderTop": "1px solid #ddd",
                       "textAlign": "center", "fontSize": "0.75rem", "color": "#888"},
                children=[
                    html.A("Methodology", href="/methodology",
                           style={"color": "#888", "textDecoration": "none"}),
                ],
            ),
        ],
    )

    @dash_app.callback(
        Output("location-messages-panel", "children"),
        Input("map-graph", "clickData"),
    )
    def show_location_messages(click_data):
        if not click_data or not click_data.get("points"):
            return html.P("Click a marker to see messages for that location.",
                           style={"color": "#888", "fontSize": "0.85rem"})

        point = click_data["points"][0]
        location_id = point["customdata"][0]
        location_name = point.get("hovertext") or f"Location {location_id}"
        return build_location_messages_panel(location_name, load_messages_for_location(location_id))

    @dash_app.callback(
        Output("comparison-graph", "figure"),
        Input("granularity", "value"),
        prevent_initial_call=True,
    )
    def update_comparison_graph(granularity):
        return build_comparison_figure(load_data("front"), load_location_data(),
                                        granularity, front_order, front_color_map)

    # Unlike the comparison chart, this one has no time axis to zoom — so
    # the date-range/slider (they're kept in sync with each other below)
    # and granularity controls filter and re-bucket its data directly.
    @dash_app.callback(
        Output("front-facet-scatter", "figure"),
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        Input("granularity", "value"),
        prevent_initial_call=True,
    )
    def update_front_facet_graph(start_date, end_date, granularity):
        return build_front_facet_figure(load_data("front"), load_location_data(),
                                         start_date, end_date, granularity, front_order)

    # Slider <-> date-picker sync for the comparison chart's time-window
    # scrubber. Circular by design (Dash's supported "circular callback"
    # pattern): dragging the slider updates the picker, editing the picker
    # snaps the slider, and each only fires downstream when its value
    # actually changes so the loop settles after one hop in each direction.
    @dash_app.callback(
        Output("date-range", "start_date"),
        Output("date-range", "end_date"),
        Input("time-slider", "value"),
        prevent_initial_call=True,
    )
    def slider_to_dates(value):
        start_offset, end_offset = value
        return _day_offset_to_date(min_date, start_offset), _day_offset_to_date(min_date, end_offset)

    @dash_app.callback(
        Output("time-slider", "value"),
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        prevent_initial_call=True,
    )
    def dates_to_slider(start_date, end_date):
        return [_days_between(min_date, start_date), _days_between(min_date, end_date)]

    @dash_app.callback(
        Output("date-range", "start_date", allow_duplicate=True),
        Output("date-range", "end_date", allow_duplicate=True),
        Input("reset-date-range", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_date_range(n_clicks):
        return min_date.date().isoformat(), max_date.date().isoformat()

    # The comparison chart always plots the full history — the slider/picker
    # above just move its visible x-axis window, and the chart's own
    # zoom/pan feeds back into them, via a third leg of the same circular
    # pattern. row=3 (the heatmap) is the "master" x-axis (make_subplots'
    # shared_xaxes ties rows 1-2 to match it — see xaxis3 below), so that's
    # the one whose range is patched/read.
    @dash_app.callback(
        Output("comparison-graph", "figure", allow_duplicate=True),
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        prevent_initial_call=True,
    )
    def dates_to_zoom(start_date, end_date):
        patched = Patch()
        patched["layout"]["xaxis3"]["range"] = [start_date, end_date]
        return patched

    @dash_app.callback(
        Output("date-range", "start_date", allow_duplicate=True),
        Output("date-range", "end_date", allow_duplicate=True),
        Input("comparison-graph", "relayoutData"),
        prevent_initial_call=True,
    )
    def zoom_to_dates(relayout_data):
        if not relayout_data:
            raise PreventUpdate
        for prefix in ("xaxis3", "xaxis2", "xaxis"):
            lo, hi = relayout_data.get(f"{prefix}.range[0]"), relayout_data.get(f"{prefix}.range[1]")
            if lo is not None and hi is not None:
                return pd.Timestamp(lo).date().isoformat(), pd.Timestamp(hi).date().isoformat()
            if relayout_data.get(f"{prefix}.autorange"):
                return min_date.date().isoformat(), max_date.date().isoformat()
        raise PreventUpdate

    return dash_app
