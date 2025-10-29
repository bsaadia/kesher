import osmnx as ox
import pandas as pd

# Step 1: Get the Gaza Strip administrative boundary polygon
gaza = ox.geocode_to_gdf("Gaza Strip")

# Step 2: Define tags for places and admin boundaries
place_tags = {"place": ["city", "town", "village", "hamlet"]}
admin_tags = {"boundary": "administrative"}

# Step 3: Query geometries strictly inside Gaza
places = ox.features_from_polygon(gaza.geometry.iloc[0], place_tags)
admins = ox.features_from_polygon(gaza.geometry.iloc[0], admin_tags)

# Step 4: Extract Hebrew names
places = places.reset_index()
admins = admins.reset_index()

places["hebrew_name"] = places["name:he"]
admins["hebrew_name"] = admins["name:he"]

# Step 5: Add type column
places["type"] = "place"
admins["type"] = "admin_boundary"

# Step 6: Merge
gazetteer = pd.concat([places[["hebrew_name", "type"]],
                       admins[["hebrew_name", "type"]]],
                      ignore_index=True)

# Drop rows without Hebrew names and remove duplicates
gazetteer = gazetteer.dropna(subset=["hebrew_name"]).drop_duplicates()

# Step 7: Save to CSV
gazetteer.to_csv("scrap/gaza_gazetteer.csv", index=False, encoding="utf-8-sig")

print("Gazetteer saved as gaza_gazetteer.csv")
