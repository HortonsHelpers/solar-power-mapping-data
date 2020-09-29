# Preprocess OSM extract into filtered subsets; and compile FiT Excels into csv.

all: osm-gb-solaronly.osm.pbf osm-gb-solaronly.xml osm-gb-solaronly.geojson osm.csv fit.csv repd.csv


# basic OSM solarfiltering -- reduces 1.5 GB to approx 2 MB
osm-gb-solaronly.osm.pbf: ../as_received/great-britain-latest.osm.pbf
	osmium tags-filter $< generator:method=photovoltaic plant:method=photovoltaic plant:source=solar -o $@

# format-shifting OSM->XML
osm-gb-solaronly.xml: osm-gb-solaronly.osm.pbf
	osmium cat $< -o $@

# format-shifting OSM->GeoJSON requires each "layer" to be exported
osm-gb-solaronly.geojson: osm-gb-solaronly.osm.pbf
	ogr2ogr -f GeoJSON -overwrite      -addfields $@ $< points           -nln merged
	ogr2ogr -f GeoJSON -update -append -addfields $@ $< lines            -nln merged
	ogr2ogr -f GeoJSON -update -append -addfields $@ $< multilinestrings -nln merged
	ogr2ogr -f GeoJSON -update -append -addfields $@ $< multipolygons    -nln merged
	ogr2ogr -f GeoJSON -update -append -addfields $@ $< other_relations  -nln merged

osm.csv: osm-gb-solaronly.xml
	python3 compile_osm_solar.py

fit.csv: ../as_received/installation_report_apr2020_part_1.xlsx
	python3 convert_fit_excel_to_csv.py

repd.csv: ../as_received/renewable-energy-planning-database-march-2020.csv
	cat $< | sed -e "s|00/01/1900||g" > $@

clean:
	rm osm.csv fit.csv osm-gb-solaronly.osm.pbf osm-gb-solaronly.xml osm-gb-solaronly.geojson

