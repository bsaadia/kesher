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

# Step 4: Extract Hebrew names and coordinates
places = places.reset_index()
admins = admins.reset_index()

# Get centroid for coordinates
places["lat"] = places.geometry.centroid.y
places["lon"] = places.geometry.centroid.x
admins["lat"] = admins.geometry.centroid.y
admins["lon"] = admins.geometry.centroid.x

places["name_he"] = places["name:he"]
admins["name_he"] = admins["name:he"]
places["name_en"] = places["name:en"]
admins["name_en"] = admins["name:en"]

# Step 5: Add type column
places["type"] = "place"
admins["type"] = "admin_boundary"

# Step 6: Merge
columns_to_keep = ["name_he", "name_en", "type", "lat", "lon"]
gazetteer = pd.concat([places[columns_to_keep],
                       admins[columns_to_keep]],
                      ignore_index=True)

# Drop rows without Hebrew names and remove duplicates
gazetteer = gazetteer.dropna(subset=["name_he", "lat", "lon"]).drop_duplicates()

# Step 7: Save to CSV
gazetteer.to_csv("scrap/gaza_gazetteer.csv", index=False, encoding="utf-8-sig")

print("Gazetteer saved as gaza_gazetteer.csv")
