import geopandas as gpd
import os

image_footprint = gpd.read_file("./model_input/1/footprint.geojson")

for file in os.listdir("./bathymetry/footprints"):
  bathy_layer_footprint = gpd.read_file(f"./bathymetry/footprints/{file}")
  if image_footprint.intersects(bathy_layer_footprint)[0]:
    print(f"{file[:-8]}.tif")