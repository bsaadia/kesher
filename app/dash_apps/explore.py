"""Interactive exploratory dashboard, embedded into the Flask server via Dash.

Mounts at ``/dash/explore/``. Provides message-volume-over-time with a
date-range picker, a time-granularity toggle, and a group-by toggle
(front vs. channel). Built to be extended with further exploratory views.
"""

import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html, Input, Output
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from models.base import engine
from models.message import Message
from models.location import Location
from models.associations import MessageLocation

# Own session factory so the dashboard stays decoupled from the request-scoped
# g.db_session lifecycle in app/__init__.py.
Session = sessionmaker(bind=engine)

URL_BASE = "/dash/explore/"

# pandas resample frequency aliases keyed by the granularity control's value.
# Month-end alias was renamed "M" -> "ME" in pandas 2.2.
_MONTH = "ME" if tuple(map(int, pd.__version__.split(".")[:2])) >= (2, 2) else "M"
FREQ = {"day": "D", "week": "W", "month": _MONTH}

# Empty-state figure so callbacks always return a valid figure.
_EMPTY_FIG = px.line(template="plotly_dark").update_layout(
    annotations=[dict(text="No messages in range", showarrow=False,
                      font=dict(size=16, color="#888"))]
)


def load_data() -> pd.DataFrame:
    """One row per (message, front) pair; front is NaN when a message has no
    located front. Columns: id, timestamp, channel, front."""
    query = (
        select(Message.id, Message.timestamp, Message.channel, Location.front)
        .outerjoin(MessageLocation, Message.id == MessageLocation.message_id)
        .outerjoin(Location, MessageLocation.location_id == Location.id)
    )
    with Session() as session:
        rows = session.execute(query).all()

    df = pd.DataFrame(rows, columns=["id", "timestamp", "channel", "front"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.dropna(subset=["timestamp"])


def build_figure(df: pd.DataFrame, start, end, granularity, group_by):
    """Filter to the selected window, aggregate counts per period per group,
    and return a stacked bar figure."""
    if df.empty:
        return _EMPTY_FIG

    mask = (df["timestamp"] >= pd.Timestamp(start)) & \
           (df["timestamp"] <= pd.Timestamp(end) + pd.Timedelta(days=1))
    df = df.loc[mask]

    if group_by == "channel":
        # Collapse the front-expansion so each message counts once per channel.
        df = df.drop_duplicates("id")
    else:  # front
        df = df.dropna(subset=["front"])

    if df.empty:
        return _EMPTY_FIG

    counts = (
        df.groupby([pd.Grouper(key="timestamp", freq=FREQ[granularity]), group_by])
        .size()
        .reset_index(name="messages")
    )

    fig = px.bar(
        counts, x="timestamp", y="messages", color=group_by,
        template="plotly_dark",
        labels={"timestamp": "", "messages": "Messages", group_by: group_by.title()},
    )
    fig.update_layout(
        barmode="stack",
        margin=dict(l=40, r=20, t=30, b=40),
        legend_title_text=group_by.title(),
        bargap=0.05,
    )
    return fig


def init_explore_dash(server):
    """Attach the exploratory Dash app to an existing Flask ``server``."""
    dash_app = Dash(
        server=server,
        url_base_pathname=URL_BASE,
        title="Explore — Tzahal Mapper",
    )

    # Load once to seed the date-picker bounds; callbacks reload live so new
    # messages from the pipeline show up on refresh.
    seed = load_data()
    if seed.empty:
        min_date = max_date = pd.Timestamp.today().normalize()
    else:
        min_date, max_date = seed["timestamp"].min(), seed["timestamp"].max()

    dash_app.layout = html.Div(
        style={"font-family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
               "padding": "1.5rem", "maxWidth": "1200px", "margin": "0 auto"},
        children=[
            html.H1("Explore message activity", style={"fontSize": "1.4rem"}),
            html.A("← Map", href="/", style={"color": "#888", "fontSize": "0.85rem"}),
            html.Div(
                style={"display": "flex", "gap": "2rem", "flexWrap": "wrap",
                       "alignItems": "center", "margin": "1.25rem 0"},
                children=[
                    html.Div([
                        html.Label("Time frame", style={"display": "block",
                                                        "fontSize": "0.8rem", "color": "#888"}),
                        dcc.DatePickerRange(
                            id="date-range",
                            min_date_allowed=min_date.date(),
                            max_date_allowed=max_date.date(),
                            start_date=min_date.date(),
                            end_date=max_date.date(),
                            display_format="D MMM YYYY",
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
                    html.Div([
                        html.Label("Group by", style={"display": "block",
                                                      "fontSize": "0.8rem", "color": "#888"}),
                        dcc.RadioItems(
                            id="group-by",
                            options=[{"label": "Front", "value": "front"},
                                     {"label": "Channel", "value": "channel"}],
                            value="front",
                            inline=True,
                            labelStyle={"marginRight": "0.75rem"},
                        ),
                    ]),
                ],
            ),
            dcc.Graph(id="volume-graph", style={"height": "600px"}),
        ],
    )

    @dash_app.callback(
        Output("volume-graph", "figure"),
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        Input("granularity", "value"),
        Input("group-by", "value"),
    )
    def update_graph(start_date, end_date, granularity, group_by):
        return build_figure(load_data(), start_date, end_date, granularity, group_by)

    return dash_app
