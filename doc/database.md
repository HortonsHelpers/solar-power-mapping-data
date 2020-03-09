% The hut23-425 database

This note documents the creation of the `hut23-425` database and the initial
deduplication of the data.

We use an "Extract-Load-Transform" methodology: Tables of the source datasets
are first uploaded from the `data/processed` directory into the schema `raw` in
the database, then post-processed in the database and saved as tables in the
default schema. (Some tables do not require post-processing and are uploaded
directly into the default schema.)

# 1. Database creation scripts

These scripts assume the existence of a local Postgres installation containing a
database called `hut23-425`. To create the database, run:

```bash
createdb hut23-425 "Solar PV database matching"
```

## Upload of source data

SQL code to create the tables and populate the database is in the `db/`
directory. To create the complete database, change to that directory and run:

```bash
psql -f make-database.sql hut23-425
```

This script will in turn call `osm.sql`, `repd.sql`, `fit.sql`, and `mv.sql`
which create and populate the following tables from the respective source data
in `../data/processed/` and add a small number of additional columns. Note that
the schema `raw` is used as a staging area for certain tables where it is
necessary to do some postprocessing. After postprocessing the working tables
will be in the default schema.

- `raw.osm`: The raw OSM data.
- `raw.repd`: The raw REPD data.
- `repd`: The REPD data, restricted to solar PV technologies.
- `fit`: The FiT data. 
- `machine_vision`: The machine vision data. 

A field, `area`, is added to the `fit` table, containing an estimate of the area
of the solar panel(s) based on the declared net capacity.

The tables `osm`, `repd`, and `mv` include a latitude and longitude for each
installation. An additional field `location` is added to these tables containing
these coordinates converted to a Postgis point.

## Primary keys for the uploaded data

### FiT: `row_id`

We presume each row of the FiT data denotes an individual installation. However,
there is no defined primary key for this dataset. To allow us to reference the
original rows later an index is added to the dataset between `raw` and
`processed`.

### REPD: `repd_id`

The source data contains a unique identifier, `Ref ID`, for each
installation. This field has been renamed to `repd_id` and used as the primary
key.

### OSM: `osm_id`

The OSM data has a unique identifier, `id`, for each row. This field has been
renamed `osm_id` and used as the primary key but note that it does not
necessarily represent a unique installation.

### Machine Vision: `mv_id`

We have added a row identifier, `mv_id`, to the pre-processed machine vision dataset. 

# 2. Preliminary matching

The table `osm_repd_id_mapping(osm_id, repd_id)` maps OSM identifiers to REPD
identifiers.

The entries in the OSM dataset were tagged (in the original data) with zero
or more REPD identifiers. These are present in the field `repd_id_str` as a
semicolon-separated list. The file `match-osm-repd.sql` “un-nests” these
identifiers as a set of rows matched to the corresponding `osm_id`. 

# 3. Deduplication of the OSM dataset

The OSM dataset contains many rows which refer to the same solar PV
installation. An OSM entry `objtype` can be one of `relation`, `way`, or `node`.
In the case of a `relation`, there may be several other entries classified as
`way` that are actually the components of the `relation`, all of which refer to
a single PV installation. There may also be severals `way`s that are part of the
same installation even though there is no unifying `relation`.

## Using the `plantref` field













