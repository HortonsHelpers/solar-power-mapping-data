# export_geometries.py
# Dan Stowell April 2020

# This script takes as input:
# (1) a CSV file as produced by db/export.sql
# (2) a GeoJSON file produced by taking our filtered OSM extract of UK PV
# and unifies them into a GeoJSON tagged with our PV data.

# How to convert the OSM extract to GeoJSON, using ogr2ogr on a linux commandline:
#    rm data/exported/osm_layers_merged.geojson
#    for layer in points lines multilinestrings multipolygons other_relations;
#       do echo "Extracting layer $layer";
#          ogr2ogr -f GeoJSON -update -append -addfields data/exported/osm_layers_merged.geojson data/exported/osm-gb-solaronly.osm.pbf $layer -nln merged;
#    done



import csv, os
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon, MultiPolygon, LineString, GeometryCollection

pvexportfpath = 'ukpvgeo_points.csv'
geometryfpath = '../raw/osm-gb-solaronly.geojson'


# load ukpvgeo_all.csv to df
inttype = pd.Int64Dtype()
df = pd.read_csv(pvexportfpath, dtype={'repd_id':inttype, 'osm_id':inttype, 'repd_cluster_id':inttype, 'osm_cluster_id':inttype, 'num_modules':inttype, 'orientation':inttype})
# load osm geojson to gdf
gdf = gpd.read_file(geometryfpath)

# summarise the geometries loaded
print("Loaded GeoJSON source, with the following geometry objects:")
print(gdf.geom_type.value_counts())

# delete columns that we don't care about. for example: the other_tags from gdf
#   DON'T YET delete the lat lon from csv.
for colname in ['other_tags', 'barrier', 'man_made', 'highway', 'landuse', 'building', 'tourism', 'amenity', 'shop', 'natural', 'leisure', 'sport', 'z_order', 'type']:
	if colname in gdf:
		del gdf[colname]

# csv: check stats on osm_id, osm_way_id and their co-occurrence --- then merge the columns
# cute row selection: gdf[~gdf.barrier.isna() & ~gdf.osm_id.isna()]
print("GDF columns:")
print(gdf.columns)
assert ( gdf.osm_id.isna() &  gdf.osm_way_id.isna()).sum()==0, "Violated expectation that no GeoJSON object can have BOTH osm_id and osm_way_id"
assert (~gdf.osm_id.isna() & ~gdf.osm_way_id.isna()).sum()==0, "Violated expectation that every GeoJSON object must have osm_id or osm_way_id"
gdf.osm_id.update(gdf.osm_way_id) # coalesce in-place - this impl assumes no overlap
del gdf['osm_way_id']
# now convert the osm_id to the same data type as in the other dataset
gdf["osm_id"] = pd.to_numeric(gdf["osm_id"])
gdf = gdf.astype({'osm_id': inttype})

# rename some columns to clarify their origin
gdf = gdf.rename(columns={'name':'osm_name'})

####################################################################
# convert lines into polygons
# https://gis.stackexchange.com/questions/321004/iterating-features-and-buffering-using-geopandas

def convert_line_to_polygon(obj):
	"NOTE: returns false if no conversion possible/needed"
	coords = obj.coords
	closed = coords[0]==coords[-1]
	if closed:
		return Polygon(coords)
	print("Warning, unclosed way (has %i points), consider inspecting it." % len(coords))
	return False

geomconverted = {'LineString': 0, 'GeometryCollection_LineString': 0, 'nonosm_Point': 0}

for index, row in gdf[gdf.geom_type=='LineString'].iterrows():
	if newgeom := convert_line_to_polygon(row.geometry):
		gdf.loc[index, 'geometry'] = newgeom
		geomconverted['LineString'] += 1

	else:
		print(row.osm_id)
print(f"Converted geometries. Converted: {geomconverted}. Results:")
print(gdf.geom_type.value_counts())

#########################################################################
# perform a join -- a right join, to capture the REPD items with no osmid
udf = gdf.merge(df, on='osm_id', how='right')

print("Items with osmid and no geom (will be dropped, assumed merged into a relation's multipol): %i" %   (udf.geometry.isna() & ~udf.osm_id.isna()).sum())
udf.drop(udf[udf.geometry.isna() & ~udf.osm_id.isna()].index, inplace=True)
print("Items with osmid and no geom (now dropped): %i" %   (udf.geometry.isna() & ~udf.osm_id.isna()).sum())

print("Items with no geom and no lat-lon (will be dropped, cannot geolocate): %i" %   (udf.geometry.isna() & udf.latitude.isna()).sum())
udf.drop(udf[udf.geometry.isna() & udf.latitude.isna()].index, inplace=True)


# the resulting items with no osm_id - are they the ones we expect? is it the same set as the entries with no geom?
print("Merged data.")
print("Items with    geometry: %i" % (~udf.geometry.isna()).sum())
print("Items without geometry: %i" %   udf.geometry.isna().sum())
print("Items with    osmid   : %i" % (~udf.osm_id.isna()).sum())
print("Items without osmid   : %i" %   udf.osm_id.isna().sum())

# the resulting items with no osm_id - assert no geom, add point geom from lat+lon
assert (~udf[udf.osm_id.isna()].geometry.isna()).sum()==0, "Rows with no osm_id should also have no geometry"

for index, row in udf[udf.osm_id.isna()].iterrows():
	udf.loc[index, 'geometry'] = Point(row['longitude'], row['latitude'])
	geomconverted['nonosm_Point'] += 1

print("Created geometries for non-osm points. Converted: %i. Results:" % geomconverted['nonosm_Point'])
print(gdf.geom_type.value_counts())

assert udf.geometry.isna().sum()==0, "After creating lat-lon points, no-one should have null geometry: we have %i" % udf.geometry.isna().sum()

# near end: delete columns latitude, longitude -- these were derived from the geometry anyway
for colname in ['latitude', 'longitude']:
	if colname in udf:
		del udf[colname]

#########################################################################
print("===========================================================================")
print("Finished filtering and merging CSV and GeoJSON data.")
print(udf.describe(exclude=gpd.array.GeometryDtype))

# write file out
udf.to_file("ukpvgeo_geometries.geojson", driver='GeoJSON')

