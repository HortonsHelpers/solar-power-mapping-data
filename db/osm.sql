/*
** Create table containing OSM database
*/

\echo Creating OSM table ...

drop table if exists raw.osm;

create table raw.osm (
  objtype        varchar(8),
  osm_id         bigint,
  username       varchar(60),
  time_created   date,
  latitude       float,
  longitude      float,
  area           float,
  capacity       float,
  modules        float,
  located        varchar(20),
  orientation    float,
  plantref       varchar(20),
  source_capacity varchar(255),
  source_obj     varchar(255),
  tag_power      varchar(15),
  repd_id_str    varchar(20),
  tag_start_date date,
  primary key (osm_id)
);

\copy raw.osm from '../data/processed/osm.csv' delimiter ',' csv header;

/* -----------------------------------------------------------------------------
** Edit table as necessary
*/

-- coerce some float columns to int, since float res is excessive (but sometimes present in the input)

alter table raw.osm
  alter column modules
    type bigint using round(modules)::bigint;
alter table raw.osm
  alter column orientation
    type integer using round(orientation)::integer;

-- our input is using kW, convert to MW for coherence with use elsewhere in the db
update raw.osm set capacity = 0.001 * capacity;

-- Create geometry columns for geographical comparison/matching
-- NB: Spatial Reference ID 4326 refers to WGS84

alter table raw.osm
  add column location geometry(Point, 4326);

update raw.osm
  set location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326);
