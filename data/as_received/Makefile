# Preprocess OSM extract into filtered subsets

all: osm-gb-solaronly.osm.pbf osm-gb-solaronly.xml osm_layers_merged.geojson compile_processed_PV_objects.csv


# basic OSM solarfiltering -- reduces 1.5 GB to approx 2 MB
osm-gb-solaronly.osm.pbf: great-britain-latest.osm.pbf
	osmium tags-filter $< generator:method=photovoltaic plant:method=photovoltaic plant:source=solar -o $@

# format-shifting OSM->XML
osm-gb-solaronly.xml: osm-gb-solaronly.osm.pbf
	osmium cat $< -o $@

# format-shifting OSM->GeoJSON requires each "layer" to be exported
osm_layers_merged.geojson: osm-gb-solaronly.osm.pbf
	ogr2ogr -f GeoJSON -overwrite      -addfields $@ $< points           -nln merged
	ogr2ogr -f GeoJSON -update -append -addfields $@ $< lines            -nln merged
	ogr2ogr -f GeoJSON -update -append -addfields $@ $< multilinestrings -nln merged
	ogr2ogr -f GeoJSON -update -append -addfields $@ $< multipolygons    -nln merged
	ogr2ogr -f GeoJSON -update -append -addfields $@ $< other_relations  -nln merged

# invoke compile py
compile_processed_PV_objects.csv: osm-gb-solaronly.xml
	python3 compile_osm_solar.py

clean:
	rm compile_processed_PV_objects.csv osm-gb-solaronly.osm.pbf osm-gb-solaronly.xml osm_layers_merged.geojson

