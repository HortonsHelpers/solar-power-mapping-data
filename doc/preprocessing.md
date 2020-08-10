Manual pre-processing datasets
===========

These are the manual data transformations made to get the files in `data/raw` from `data/as_received`.

FiT
----

1. Combine the 3 spreadsheets into one
2. Remove rows above header
3. Convert to csv
4. Save as `data/raw/fit.csv`

OSM (csv)
----

There are sometimes manual edits needed, to fix typos in the uncontrolled OSM source data. We have fixed many of them, and also caught them in the preprocessing of `compile_osm_solar.py`, but there could be others in future OSM data releases. Here are examples of edits we made:

1. Example edits:

    2. Changed "14Synthetic"... to "14" for id=7784835486 in generator:solar:modules column.
    2. Changed "8node 0" to "8" for id=7772459006 in generator:solar:modules column
    2. Changed "36node 0" to "36" for id=7772459035 in generator:solar:modules column
    2. Changed "17generator:method" to "17" for id=7791014395 in generator:solar:modules column
    2. For object id=835531116, move "SE" from wrong column generator:solar:modules to orientation

3. Save as `data/raw/osm.csv`

REPD
----

1. Delete one unusual date/time cell: "00/01/1900"
2. Save as `data/raw/repd.csv`.

Machine vision dataset
-----

No changes. Save as `data/raw/machine_vision.geojson`.
