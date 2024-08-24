import pandas as pd
import geopandas as gpd

aoi = gpd.read_file("/home/ryan/sar_vessel_detect/model_input/1/footprint.geojson")
df = pd.read_csv("/home/ryan/sar_vessel_detect/src/out.csv")

minx = aoi.bounds.minx.iloc[0]
maxy = aoi.bounds.maxy.iloc[0]
df['utm_long'] = minx + (df.detect_scene_column * 10)
df['utm_lat'] = maxy - (df.detect_scene_row * 10)
gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df['utm_long'], df['utm_lat']), crs=aoi.crs)
gdf_reproj = gdf.to_crs(epsg=4326)

# TODO: To PostGIS we go!!