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
	SELECT DISTINCT osm.objtype as osm_objtype, osm.osm_id,
		repd.repd_id, repd.site_name as repd_site_name,
		repd.capacity::float as "capacity_repd_MWp", osm.capacity * 0.001 as "capacity_osm_MWp",
	COALESCE(osm.latitude, repd.latitude) as latitude,
	COALESCE(osm.longitude, repd.longitude) as longitude,
	osm.area as area_sqm, osm.located, osm.orientation, osm.tag_power as osm_power_type, osm.tag_start_date as osm_tag_start_date,
	osm.modules as num_modules, -- osm.source_obj as osm_source_obj, osm.source_capacity as osm_source_capacity,
	repd.dev_status_short, repd.operational, repd.old_repd_id,
	osm.master_osm_id as osm_cluster_id, repd.master_repd_id as repd_cluster_id,
	matches.match_rule
	FROM (matches
		FULL JOIN repd ON (matches.master_repd_id=repd.repd_id
			AND repd.dev_status_short NOT IN ('Abandoned', 'Application Refused', 'Application Withdrawn',  'Planning Permission Expired')
			AND match_rule NOT IN ('4', '4a'))   -- skip matches that were "schemes"
		FULL JOIN osm ON (matches.master_osm_id=osm.osm_id
			))
	WHERE ((osm_id IS NOT NULL) OR (repd.dev_status_short IS NULL) OR (repd.dev_status_short NOT IN ('Abandoned', 'Application Refused', 'Application Submitted', 'Application Withdrawn',  'Planning Permission Expired')))
	ORDER BY repd.repd_id, osm.osm_id;

\copy "tmp_export_pvgeo" TO '../data/exported/ukpvgeo_points_merged_deduped_osm-repd_all.csv' WITH DELIMITER ',' CSV HEADER;

\copy (SELECT * FROM tmp_export_pvgeo WHERE (osm_id = osm_cluster_id OR osm_cluster_id IS NULL OR osm_id IS NULL) AND (repd_id = repd_cluster_id OR repd_cluster_id IS NULL OR repd_id IS NULL)) TO '../data/exported/ukpvgeo_points_merged_deduped_osm-repd_clusters.csv' WITH DELIMITER ',' CSV HEADER;


