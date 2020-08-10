/*
** Area-adaptive threshold function for clustering PV geodata items
** July 2020
** Author: Dan Stowell
**
** The function returns a distance threshold which is related to the 
** geometry surface areas (sizes) of the two points being compared.
**
** If area is unknown, we use a heuristic estimate based on capacity similar to "2 hectares per MW";
** The exact ratio is very close to the correlation seen in the paper.
**
*/

CREATE FUNCTION area_adaptive_threshold(area1 float, area2 float, capacity1 float, capacity2 float)
RETURNS float AS $$
BEGIN

RETURN LEAST(1500, GREATEST(10,
	2 * SQRT(GREATEST(
		GREATEST(area1, capacity1 * 20000),
		GREATEST(area2, capacity2 * 20000)
	))));
END; $$
LANGUAGE plpgsql IMMUTABLE LEAKPROOF PARALLEL SAFE;

