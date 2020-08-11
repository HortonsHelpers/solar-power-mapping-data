# export data. You can export AND analyse by invoking "make all".

ukpvgeo_geometries.geojson: ukpvgeo_points.csv ../raw/osm-gb-solaronly.geojson
	python3 export_geometries.py

all: ukpvgeo_geometries.geojson plot_analyse_exported.pdf

plot_analyse_exported.pdf: ukpvgeo_points.csv
	python3 analyse_exported.py

clean:
	rm ukpvgeo_geometries.geojson plot_analyse_exported.pdf

