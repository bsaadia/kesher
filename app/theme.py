"""Shared visual-design constants (palette, typography) for the Dash app.

Single Python-side source of truth for hex values used in Plotly figures and
inline style={} dicts in app/dash_apps/explore.py. The CSS custom properties
in app/assets/style.css and the standalone <style> block in
app/templates/methodology.html use the same literal hex values, kept in sync
by hand — there is no shared mechanism across the Python/Jinja/CSS boundary.
"""

# --- Core palette -----------------------------------------------------
BG_PAGE = "#F5EFE1"        # page background
BG_PANEL = "#FBF7EC"       # card/panel background (messages panel, popovers)
BORDER = "#C9BFA0"         # hairline border / divider
TEXT_PRIMARY = "#2E2C24"   # primary text
TEXT_MUTED = "#6B6650"     # secondary / muted text (captions, labels)
ACCENT_OLIVE = "#5B6B44"   # primary accent (nav, active states, links)
ACCENT_OLIVE_MUTED = "#98A17E"  # desaturated olive for less-prominent UI chrome (slider)
ACCENT_RUST = "#A85C32"    # secondary accent (highlights, key numbers)

# --- Front legend (fixed, canonical order: Gaza, Judea & Samaria, Lebanon,
# Syria, Yemen, Iran) ----------------------------------------------------
# Lebanon/Iran were both a dark blue-grey in the original earth-tone spec and
# read as near-identical on the comparison bars — shifted to a clear blue and
# a muted plum (then swapped with each other again per feedback, so Syria
# reads purple and Iran reads red/brick). Judea & Samaria/Yemen were both
# yellow-brown-ish and also collided with each other and with Gaza — shifted
# Judea & Samaria to a distinct burnt-orange and Yemen to a lighter
# grey-beige. Gaza is a clear, saturated forest green — not the app's olive
# accent (too similar to its original color) and not too muted/washed out.
# The DB's actual front value is "Gaza Strip" (not "Gaza") — every previous
# attempt at this color used the wrong dict key, so it silently fell back to
# FRONT_COLOR_FALLBACK below instead of ever applying.
FRONT_COLORS = {
    "Gaza Strip": "#1B5E20",
    "Judea & Samaria": "#C97B2A",
    "Lebanon": "#3D6B8C",
    "Syria": "#5C4770",
    "Yemen": "#B9A883",
    "Iran": "#9C4A36",
}
FRONT_COLOR_FALLBACK = "#8A8570"  # neutral warm-grey for any unrecognized front

# --- Sequential heat/density scale (low -> high message count), replacing
# the built-in "YlOrRd" colorscale on the map, comparison heatmap, and
# front-facet scatter (all three now share one scale for a consistent
# reading of "low to high" across every chart) -----------------------------
HEAT_SCALE = [
    [0.00, "#E9DCC0"],
    [0.25, "#C7A76B"],
    [0.50, "#B8892B"],
    [0.75, "#A85C32"],
    [1.00, "#7A3420"],
]

# Slightly more saturated/deepened variant of HEAT_SCALE, used only for the
# messages-per-location ratio heatmap, where the base scale read as too washed
# out against the themed (no longer plain white) chart canvas.
HEAT_SCALE_HEATMAP = [
    [0.00, "#E6D2A0"],
    [0.25, "#C29A4E"],
    [0.50, "#A87A1E"],
    [0.75, "#96431B"],
    [1.00, "#6B2A12"],
]

# --- Typography ----------------------------------------------------------
FONT_SANS = "-apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif"
FONT_MONO = "\"SFMono-Regular\", Consolas, \"Liberation Mono\", Menlo, monospace"

# --- Shared Plotly figure theme -------------------------------------------
# Applied via _apply_theme() in explore.py so charts read as part of the same
# design system as the surrounding page instead of Plotly's default white
# canvas — background, font, and gridline color only; no trace/layout logic.
# paper/plot background match the bare page (BG_PAGE), not the panel tone
# (BG_PANEL) — charts sit directly on the page rather than inside their own
# card, so matching the page avoids a visible seam between chart canvas and
# surrounding background. Font is monospace, matching the app's "field
# report" data-label treatment.
PLOTLY_LAYOUT = dict(
    paper_bgcolor=BG_PAGE,
    plot_bgcolor=BG_PAGE,
    font=dict(family=FONT_MONO, color=TEXT_PRIMARY),
)
