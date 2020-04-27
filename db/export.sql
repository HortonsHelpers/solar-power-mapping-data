/*
** Solar PV database export to CSV etc
** April 2020
** Author: Dan Stowell
*/

-- "Suggested REPD IDs for OSM"
CREATE TEMP TABLE "tmp_export_osm_repd" AS
SELECT match_rule, osm.objtype, osm.osm_id, osm.latitude as "osm_latitude", osm.longitude as "osm_longitude", osm.repd_id_str as "osm_repd_id", repd.*
	FROM matches
		LEFT JOIN repd ON matches.master_repd_id=repd.repd_id
		LEFT JOIN osm ON matches.master_osm_id=osm.osm_id
	WHERE osm.repd_id_str IS NULL   -- this one excludes all OSM items with no listed REPD
		OR (NOT osm.repd_id_str=cast(repd.repd_id as varchar(10)))   -- and this one adds in the ones present but mismatching
	ORDER BY (match_rule IN ('4', '4a')), repd.repd_id;

\copy "tmp_export_osm_repd" TO '../data/exported/osm_repd_proposed_matches.csv' WITH DELIMITER ',' CSV HEADER;

-- "Grand unified [over osm & repd] CSV of PV geolocations"
CREATE TEMP TABLE "tmp_export_pvgeo" AS
	SELECT repd.old_repd_id, repd.repd_id, osm.objtype as osm_objtype, osm.osm_id, repd.capacity as capacity_repd, osm.capacity * 0.001 as capacity_osm, repd.dev_status_short, repd.operational,
	COALESCE(osm.latitude, repd.latitude) as latitude,
	COALESCE(osm.longitude, repd.longitude) as longitude,
	osm.area, osm.located, osm.orientation, osm.tag_power as osm_power_type, osm.tag_start_date as osm_tag_start_date, matches.match_rule
	FROM (matches
		FULL JOIN repd ON (matches.master_repd_id=repd.repd_id
			AND repd.dev_status_short NOT IN ('Abandoned', 'Application Refused', 'Application Withdrawn',  'Planning Permission Expired')
			-- AND repd.repd_id NOT IN (1892, 1894, 6750))   -- skip three named "schemes"
			AND match_rule NOT IN ('4', '4a'))   -- skip matches that were "schemes"
		FULL JOIN osm ON matches.master_osm_id=osm.osm_id)
	WHERE dev_status_short IS NULL OR
			repd.dev_status_short NOT IN ('Abandoned', 'Application Refused', 'Application Withdrawn',  'Planning Permission Expired')
	ORDER BY repd.repd_id, osm.osm_id;

\copy "tmp_export_pvgeo" TO '../data/exported/ukpvgeo_points_merged_deduped_osm-repd.csv' WITH DELIMITER ',' CSV HEADER;


