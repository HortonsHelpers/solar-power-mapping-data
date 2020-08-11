#!/usr/bin/env python

# Script to parse an OSM XML extract for solar PV data.
# Dan Stowell, 2019-2020.

import os, sys, csv, subprocess, re
from functools import reduce
from xml import sax
import numpy as np

from matplotlib.path import Path
from scipy.spatial import KDTree as kdtree

import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt

############################################
# User configuration:

# do_osmium = True   # if False, it won't try to filter the input OSM file
# osmsourcefpath = os.path.expanduser('~/osm/great-britain/great-britain-200729.osm.pbf')

do_osmium = False
osmsourcefpath = "osm-gb-solaronly.xml"

# The extract must ALREADY have been processed by osmium to filter down to just the generator:method=photovoltaic items.
# Here's what I do:
# osmium tags-filter ~/osm/great-britain/great-britain-200729.osm.pbf generator:method=photovoltaic plant:method=photovoltaic plant:source=solar -o  ~/osm/solarsearch/gb-solarextracts/gb-200729-solar-withreferenced.xml
# In the public scripts, this is all included in the work done by the makefile


############################################
# Helper functions:

earthradius = 6364380.0  # earth radius (m) at Manchester
degrees_to_metres = 2 * np.pi * earthradius / 360
def angular_area_to_sqm(anga, latitude_deg):
	"""Use simple angular calculation to approximately convert angular areas (calculated from GPS coords) to areas in square metres.
	WARNING: APPROXIMATE. Uses spherical assumptions, and does not know about tilt of objects."""
	latitude_correction = np.cos(np.radians(latitude_deg)) # 53.4427
	return degrees_to_metres * degrees_to_metres * latitude_correction * anga

def PolyArea(x,y):
	"Calculate area of a polygon from its coordinates (shoelace formula)"
	return 0.5*np.abs(np.dot(x,np.roll(y,1))-np.dot(y,np.roll(x,1)))  # https://stackoverflow.com/questions/24467972/calculate-area-of-polygon-given-x-y-coordinates

def guess_kilowattage(anobj):
	"This should NOT NORMALLY BE USED since it is really only a rule of thumb."
	if not anobj['calc_area']:
		return 1.
	else:
		return anobj['calc_area'] * 0.15

regex_numbers_semicolon_start = re.compile('^([0-9;]*).*')

compasspoints = {
	'N':     0,
	'NNE':  22.5,
	'NE':   45,
	'ENE':  67.5,
	'E':    90,
	'ESE': 112.5,
	'SE':  135,
	'SSE': 157.5,
	'S':   180,
	'SSW': 202.5,
	'SW':  225,
	'WSW': 247.5,
	'W':   270,
	'WNW': 292.2,
	'NW':  315,
	'NNW': 337.5,
	# unconventional but seen in data:
	'NORTH':   0,
	'NORTHEAST':   45,
	'NORTH_EAST':   45,
	'EAS':    90,                   # TEMPORARY fix for wonky entry
	'EAST':    90,
	'SOUTHEAST':    135,
	'SOUTH_EAST':    135,
	'SOUTH':  180,
	'SOUTHWEST':    225,
	'SOUTH_WEST':    225,
	'WEST':   270,
	'NORTHWEST':   315,
	'NORTH_WEST':   315,
}

##############################################################################
# The main routine, which progressively reacts to XML content as it is loaded:

class SolarXMLHandler(sax.handler.ContentHandler):
	"""Parses solar PV data from OSM XML. After this has finished, the 'objs' member is a list of processed PV objects (panels as well as plants).
	Note that after the initial parse of the XML, you then need to call postprocess() which will propagate information down from relation-containment and geographic-containment."""
	def __init__ (self):
		sax.handler.ContentHandler.__init__(self)
		self.curitem = None
		self.objs = []
		# these value-stores are for intermediate processing of relationships (e.g. the parent way/rel to know their own accumulated contents) - they are not used as the output data.
		self.nodedata = {}
		self.waydata = {}
		self.reldata = {}

	def startElement (self, name, attrs):
		if name in ['node', 'way', 'relation']: # start a new "object" with empty tags
			self.curitem = {'id': attrs['id'], 'timestamp': attrs['timestamp'], 'user': attrs.get('user', ''), 'tags':{}, 'objtype': name}
		if name == 'node':
			self.curitem['lat'] = float(attrs['lat'])
			self.curitem['lon'] = float(attrs['lon'])
		elif name == 'way':
			self.curitem['nodes'] = []
		elif name == 'relation':
			self.curitem['nodes'] = []
			self.curitem['ways'] = []
			self.curitem['relations'] = []
		elif name == 'tag':
			self.curitem['tags'][attrs['k']] = attrs['v']
		elif name == 'nd': # This is a node reference from within a way
			self.curitem['nodes'].append(attrs['ref'])
		elif name == 'member': # This is a node/way/rel reference from within a relation
			if attrs['type'] == 'way':
				self.curitem['ways'].append({'ref':attrs['ref'], 'role':attrs['role']})
			elif attrs['type'] == 'relation':
				self.curitem['relations'].append({'ref':attrs['ref'], 'role':attrs['role']})
			elif attrs['type'] == 'node':
				self.curitem['nodes'].append({'ref':attrs['ref'], 'role':attrs['role']})
			else:
				raise ValueError("This script does not know how to handle the following member-type found in relation %s: '%s'" % (self.curitem['id'], attrs['type']))

	def endElement(self, name):
		if name in ['node', 'way', 'relation']: # finish off, and store, the "object"
			curitem = self.curitem # for speed

			if ('highway' in curitem['tags']) and (curitem['tags']['highway']=='turning_circle'):
				raise ValueError("Data contains highway=turning_circle items. Are you sure this OSM data has been preprocessed to strip it down only to the photovoltaics?")

			# Cache the object data for use in lookups etc (NOT for output, these data structures - actually "curitem" is where the data for output live.)
			datacache = {
				'node': self.nodedata,
				'way': self.waydata,
				'relation': self.reldata,
			}[name]
			if curitem['id'] in datacache:
				raise ValueError("datacache seems to encounter a duplicate item: type %s, id %i" % (name, curitem['id']))
			datacache[curitem['id']] = {}
			datacacheitem = datacache[curitem['id']]

			if curitem['objtype']=='node':
				datacacheitem['lat'] = curitem['lat']
				datacacheitem['lon'] = curitem['lon']
				curitem['calc_area'] = 0   # TODO there may be a tag telling you the area; else, as a node, it's useful to make clear we have no area estimate

			elif curitem['objtype']=='way':
				latlist = [self.nodedata[nodeid]['lat'] for nodeid in curitem['nodes']]
				lonlist = [self.nodedata[nodeid]['lon'] for nodeid in curitem['nodes']]
				datacacheitem['outlinepath'] = Path([_ for _ in zip(latlist, lonlist)])
				# calculate its centroid as mean(nodes)
				curitem['lat'] = np.mean(latlist)
				curitem['lon'] = np.mean(lonlist)
				datacacheitem['lat'] = curitem['lat']
				datacacheitem['lon'] = curitem['lon']
				# calculate its area using PolyArea
				curitem['calc_area'] = PolyArea(latlist, lonlist)
				# convert to square metres
				curitem['calc_area'] = round(angular_area_to_sqm(curitem['calc_area'], curitem['lat']), 1)
				datacacheitem['calc_area'] = curitem['calc_area']

			elif curitem['objtype']=='relation':
				datacacheitem['relations'] = curitem['relations']
				datacacheitem['ways'] = curitem['ways']
				datacacheitem['nodes'] = curitem['nodes']
				datacacheitem['calc_area'] = 0
				# NB most of the relationship-handling comes at the end in postprocess()

			####################################
			# Processing tags to log a PV object
			if (curitem['tags'].get('power')=='generator' and curitem['tags'].get('generator:method')=='photovoltaic') \
			or (curitem['tags'].get('power')=='plant'     and (curitem['tags'].get('plant:method')=='photovoltaic' or curitem['tags'].get('plant:source')=='solar')):

				for k,v in curitem['tags'].items():
					# In here we aim to process ALL KNOWN tags, including irrelevant ones, so that no information is lost
					ok = True
					if k=='power':
						curitem['tag_power'] = v
					elif k in ['generator:output:electricity', 'plant:output:electricity']:
						v = v.replace(",", ".").upper()
						if v in ['YES', 'SMALL_INSTALLATION']:
							pass
						elif v.endswith(" W"):
							curitem['calc_capacity'] = float(v[:-2]) * 0.001
						elif v.endswith(" KW"):
							curitem['calc_capacity'] = float(v[:-3])
						elif v.endswith(" MW"):
							curitem['calc_capacity'] = float(v[:-3]) * 1000
						elif v.endswith(" MWP"): # NB probably not possible to make use of difference between MW and MWp
							curitem['calc_capacity'] = float(v[:-3]) * 1000
						elif v.endswith("KW"):
							curitem['calc_capacity'] = float(v[:-2])
						elif v.endswith("MW"):
							curitem['calc_capacity'] = float(v[:-2]) * 1000
						else:
							ok = False
					elif k in ['location', 'generator:place', 'generator:location']:
						if v=='rooftop':
							v = 'roof'
						curitem['location'] = v
					elif k in ['source', 'source:geometry']:
						curitem['source_obj'] = v.replace(",", ";")
					elif k in ['source:generator:output:electricity', 'source:plant:output:electricity', "source:power:output", "source:output", "source:power"]:
						if v=='REPD Open Data':
							v = 'repd'
						curitem['source_capacity'] = v.replace(",", ";")
					elif k=='note':
						if v=='roof household':
							curitem['location'] = 'roof'
						else:
							pass # TODO check all unhandled "note", see if they're OK
					elif k=='notional_area':
						if curitem['calc_area'] != 0:
							#TODO consider: print("  WARNING: skipping notional_area for %s %s because calc_area already filled in" % (curitem['objtype'], curitem['id']))
							pass
						if v.endswith(' sq m'):
							try:
								curitem['calc_area'] = float(v[:-5].replace(',', '.', ))
							except:
								print("Couldn't handle this notional_area: " + v)
						else:
							ok = False
					elif k in ['direction', 'generator:orientation', 'orientation']:
						v = v.replace('`', '').upper()  # some people write it this way
						if v in compasspoints:
							curitem['orientation'] = compasspoints[v]
						elif v in ['ESW']:
							pass # uninterpretable case seen in data... so skip
						elif v in ['FLAT']:
							pass # flat-mounted items have no orientation
						else:
							try:
								curitem['orientation'] = int(v) # NB there could of course be parse failures here
							except ValueError:
								print("Un-parseable orientation value in %s %s: %s=%s" % (curitem['objtype'], curitem['id'], k, v))
					elif k=='pv_module_array':
						splitvals = v.split(" by ")
						if len(splitvals)==2:
							curitem['generator:solar:modules'] = int(splitvals[0]) * int(splitvals[1])
						else:
							ok = False
					elif k in ['modules', 'generator:solar:modules', 'generator:modules']:
						if v=='unknown':
							v=''
						else:
							# It's quite common (for some UI reason) to get typos in this field with characters pasted after the initial digits. We trim them off.
							v = regex_numbers_semicolon_start.sub('\\1', v)
						if ';' in v:
							v = str(reduce(lambda a, b: a+b, map(int, v.split(';')))) # entries could be e.g. "7;5;2" and here we reduce them to a single integer sum
						curitem['generator:solar:modules'] = v
					#elif k=='':
					#elif k=='':
					#elif k=='':
					#elif k=='':
					#elif k=='':
					#elif k=='':
					#elif k=='':
					elif k in [
# Here are ALL the ones we copy into the output data unedited
'start_date',
'repd:id',
						]:
						curitem['tag_%s' % k] = v
					elif k in [
# Here are ALL the ones we don't need information from:
'generator',
'generator:source',
'generator:method',
'generator:type',
'generator:output',
'generator:note',
'generator:strings',
'generator:output:biogas',
'generator:output:hot_water',
'generator:plant',
'plant:source',
'plant:method',
'plant:type',
'power_source',
'note:generator:output:electricity',
'voltage',
'fixme',
'earliest_start_date',
'latest_start_date',
'amenity',
'capacity',
'floating',
'area',
'ref',
'website',
'alt_name',
'url',
'landcover',
'email',
'fax',
'postal_code',
'phone',
'site',
'surface',
'notes',
'industrial',
'listed_status',
'survey_date',
'man_made',
'barrier',
'fence_type',
'height',
'shop',
'wheelchair',
'sport',
'brand',
'leisure',
'frequency',
'manufacturer',
'architect',
'HE_ref',
'note_2',
'survey:date',
'mapillary',
'natural',
'construction',
'farmland',
'opening_hours',
	] or k.split(':')[0] in [
'source',  # NB there are lots of different source tags. Here we're suppressing any leftovers, even though we may use specific source tags already.
'operator',
'owner',
'description',
'contact',
'name',
'fence',
'social_facility',
'flickr',
'highway',
'landuse',
'fhrs',
'layer',
'ref',
'level',
'wikimedia_commons',
'wikidata',
'wikipedia',
'geograph',
'type', # rel multipolygon
'tourism',
'building',
'addr',
'roof',
'demolished',
'indoor',
]:
						pass
					else:
						ok = False

					if not ok:
						astr = "Un-recognised tag in %s %s: %s=%s" % (curitem['objtype'], curitem['id'], k, v)
						print(astr)
						#raise ValueError(astr)

					# TODO also try to calc_type: rooftop or infarm (location=roof; large size) or unknown

				if curitem['tag_power']=='plant': # We store the power-plant's ID info in a form which will be easy to propagate down to child members
					curitem['plantref'] = (curitem['objtype'], curitem['id'])

				# OK now store it - we only need to store top-level PV items, child-nodes etc are not needed except for the data stored elsewhere
				self.objs.append(self.curitem)


			self.curitem = None      # NB we need to clear "curitem" in ALL cases where it was a node/way/item, NOT just if it's a PV item processed.

	def postprocess(self):
		"""
		This MUST be called, once, after the XML has been loaded.
		It:
		- ensures relation-members know about their parent object (incl. the plantref if parent is plant);
		- calculates the total area of each relation;
		- calculates the centroid of each relation;
		- performs spatial containment queries to label solar panels as members of a plant (i.e. plantref) if they're geographically inside them.
		"""
		# Find all objects that are relations and also plants. Then push down the metadata through their children (only for the temporary data), and also calculate the area for the parents.
		rels_postprocessed = 0
		self.plantoutlines = [] # {lat, lon, outlinepath, plantref} a list of ways that are either plants themselves, or non-inner members of plant relations; i.e. potential geo containers for panels
		for curitem in self.objs:
			if curitem['tag_power']=='plant' and curitem['objtype']=='way':
				self.plantoutlines.append({'lat': curitem['lat'], 'lon': curitem['lon'], 'outlinepath': self.waydata[curitem['id']]['outlinepath'], 'plantref': curitem['plantref']})
			if curitem['tag_power'] in ['plant', 'generator'] and curitem['objtype']=='relation':
				if curitem['tag_power']=='plant':
					plantitem = curitem
					plantref = ('relation', curitem['id'])
				else:
					plantitem = None
					plantref = None
				curitem['calc_area'] = 0
				self._recurse_relation_info(curitem, plantitem, plantref)
				rels_postprocessed += 1

		print("Postprocessed %i power=* relations" % rels_postprocessed)
		print("Plant outlines for geo containment search: %i" % len(self.plantoutlines))
		plantoutlines_kdtree = kdtree([[item['lat'], item['lon']] for item in self.plantoutlines])
		# Now, for every generator object that DOESN'T have a plantref, we find its nearest-neighbour potential-containers and check for containment
		for curitem in self.objs:
			if curitem['tag_power']=='generator' and not curitem.get('plantref', None):
				for distance, arrayposition in zip(*plantoutlines_kdtree.query([curitem['lat'], curitem['lon']], 3, distance_upper_bound=1)):
					if distance != np.inf:
						if self.plantoutlines[arrayposition]['outlinepath'].contains_point([curitem['lat'], curitem['lon']]):
							curitem['plantref'] = self.plantoutlines[arrayposition]['plantref']
							#print("       spatially inferred generator %s/%s belongs to plant %s" % (curitem['objtype'], curitem['id'], curitem['plantref']))

		if False: # This should NOT NORMALLY be activated. It inserts "guesstimate" power capacities for small-scale solar PV
			for curitem in self.objs:
				if curitem['tag_power']=='generator' and curitem.get('calc_capacity', 0)==0 and not curitem.get('plantref', None):
					curitem['calc_capacity'] = guess_kilowattage(curitem)


	def _recurse_relation_info(self, curitem, plantitem, plantref):
		"""Pushes down through relations' members, for two reasons: to compile their areas onto the parent, and to propagate the parent plant reference down to all.
		You will call it with curitem==plantitem for plants, and plantitem=None for gens; then the recursion keeps plantitem fixed and alters the immediate curitem."""
		# first we recurse into the child relations - the ways and rels will then add their area to our plantitem
		#print("")
		#print("_recurse_relation_info(curitem=%s, plantitem=%s, plantref=%s)"  % (curitem, plantitem, plantref))
		for childinfo in curitem['relations']:
			therel = self.reldata[childinfo['ref']]
			if 'plantref' in therel:
				raise ValueError("Suspicious recursion: while analysing a plant relation (%i) we found a child rel (%i) which already has plantref set: %s" % (plantitem['id'], childid, str(therel['plantref'])))
			else:
				self._recurse_relation_info(therel, plantitem, plantref)
		# now we grab all area info from one-level-down, and also push the plantref down one level
		latslist = []
		lonslist = []
		for childtype, childlist, childdatacache in [
			('node',     curitem['nodes'],     self.nodedata),
			('way',      curitem['ways'],      self.waydata),
			('relation', curitem['relations'], self.reldata),
			]:
			for childinfo in childlist: # each is a dict with 'ref' and 'role'
				childobj = childdatacache[childinfo['ref']]
				latslist.append(childobj['lat'])
				lonslist.append(childobj['lon'])
				multiplier = [1, -1][childinfo['role']=='inner']  # how to subtract inner-areas
				curitem['calc_area'] += multiplier * childobj.get('calc_area', 0)
				if plantref:
					childobj['plantref'] = plantref
				#if childtype=='way':
				#	print("             from way %s we add area %g" % (childinfo['ref'], multiplier * childobj['calc_area']))
				if childtype=='way' and childinfo['role']!='inner' and plantref:
					self.plantoutlines.append({'lat': childobj['lat'], 'lon': childobj['lon'], 'outlinepath': self.waydata[childinfo['ref']]['outlinepath'], 'plantref': plantref})
		curitem['lat'] = np.mean(latslist)
		curitem['lon'] = np.mean(lonslist)


##############
# let's go!

if do_osmium:
	infp = subprocess.Popen(["osmium", "tags-filter", osmsourcefpath, "generator:method=photovoltaic", "plant:method=photovoltaic", "plant:source=solar", "-o", "-", "-f", "xml"],
			stdout=subprocess.PIPE).stdout
else:
	infp = open(osmsourcefpath, 'rb')

parser = sax.make_parser()
handler = SolarXMLHandler()
parser.setContentHandler(handler)
parser.parse(infp)
infp.close()
handler.postprocess()

# find all attribs in use
allattribs = set()
for obj in handler.objs:
	allattribs = allattribs.union(set(obj))
allattribs = allattribs.difference(set(['nodes', 'ways', 'relations', 'tags']))

# some overcomplex coding to sort attributes in the way I want
attribstarters = ['objtype', 'id', 'user', 'timestamp', 'lat', 'lon']
def attribsorter(a):
	if a in attribstarters:
		return "a_%i" % attribstarters.index(a)
	else:
		return "b_%s" % a
allattribs = sorted(list(allattribs), key=attribsorter)

if False:
	print()
	print("All object attributes in play:")
	for anattrib in allattribs:
		print(anattrib)
	print()

# output happy stats
osmtotalobjs = len(handler.objs)
print("")
print("####################################################################")
print(os.path.basename(osmsourcefpath))
print("parsed %i OSM objects (%i nodes, %i ways, %i relations)" % (osmtotalobjs,
	len([_ for _ in handler.objs if _['objtype']=='node']),
	len([_ for _ in handler.objs if _['objtype']=='way']),
	len([_ for _ in handler.objs if _['objtype']=='relation'])
	))
print("")


# collect the unique REPD identifiers
repds_used = []
for item in handler.objs:
	if item.get('tag_repd:id', False):
		repds_used.extend(item['tag_repd:id'].split(';'))

readable = "standalone"
subset = [_ for _ in handler.objs if _['tag_power']=='generator' and not _.get('plantref', None)]
print("Solar PV panel items (power=generator) (%s):" % readable)
print("   %i in total"                                                                    % len([_ for _ in subset]))
print("   %g sq km total surface area"  % (1e-6 * np.sum([_['calc_area']                           for _ in subset])))
print("   %g MW total generating capacity (NB metadata will be v incomplete for this)" % (1e-3 * np.sum([_.get('calc_capacity',0)             for _ in subset])))
print("   %i nodes with no sqm tagged (could presume 'domestic', but needs more tagging)" % len([_ for _ in subset if    _['calc_area']==0]))
print("   %i areas <= 30 sqm (could presume 'domestic')"                                  % len([_ for _ in subset if  0<_['calc_area']<=30]))
print("   %i areas 30--2000 sqm (could presume 'commercial' or part of array)"            % len([_ for _ in subset if 30<_['calc_area']<=2000]))
print("   %i areas > 2000 sqm (inspect to see if should really be tagged 'solar farm')"   % len([_ for _ in subset if    _['calc_area']>2000]))

readable = "within a farm"
subset = [_ for _ in handler.objs if _['tag_power']=='generator' and     _.get('plantref', None)]
print("Solar PV panel items (power=generator) (%s):" % readable)
print("   %i in total"                                                                    % len([_ for _ in subset]))
print("   %g sq km total surface area"  % (1e-6 * np.sum([_['calc_area']                           for _ in subset])))
print("   %i nodes with no sqm tagged"                                                    % len([_ for _ in subset if    _['calc_area']==0]))
print("   %i areas <= 30 sqm"                                                             % len([_ for _ in subset if  0<_['calc_area']<=30]))
print("   %i areas 30--2000 sqm"                                                          % len([_ for _ in subset if 30<_['calc_area']<=2000]))
print("   %i areas > 2000 sqm (inspect to see if should really be tagged 'solar farm')"   % len([_ for _ in subset if    _['calc_area']>2000]))

print("Solar PV farm items (power=plant):")
print("   %i in total"                                                                    % len([_ for _ in handler.objs if _['tag_power']=='plant']))
print("   %i have REPD identifier tagged"                                                 % len([_ for _ in handler.objs if _['tag_power']=='plant' and _.get('tag_repd:id', False)]))
print("        (%i REPD identifiers encountered)"                                         % len(repds_used))
print("   %g sq km total surface area"  % (1e-6 * np.sum([_['calc_area']                           for _ in handler.objs if _['tag_power']=='plant'])))
print("   %g MW total generating capacity"  % (1e-3 * np.sum([_.get('calc_capacity',0)             for _ in handler.objs if _['tag_power']=='plant'])))
print("   %i nodes with no sqm tagged (needs more tagging)"                               % len([_ for _ in handler.objs if _['tag_power']=='plant' and    _['calc_area']==0]))
print("   %i areas <= 30 sqm - not including nodes"                                       % len([_ for _ in handler.objs if _['tag_power']=='plant' and  0<_['calc_area']<=30]))
print("   %i areas 30--2000 sqm"                                                          % len([_ for _ in handler.objs if _['tag_power']=='plant' and 30<_['calc_area']<=2000]))
print("   %i areas > 2000 sqm"                                                            % len([_ for _ in handler.objs if _['tag_power']=='plant' and    _['calc_area']>2000]))


def csvformatspecialfields(k, v):
	"special formatting sometimes needed"
	if k=='plantref':
		if not v: return ''
		return "%s/%s" % v
	return v

try:
	with open("osm.csv", 'w', buffering=1) as outfp:
		outfp.write(",".join(allattribs) + "\n")
		for obj in handler.objs:
			outfp.write(",".join(map(str, [csvformatspecialfields(anattrib, obj.get(anattrib, '')) for anattrib in allattribs])) + "\n")
except:
	os.rename("osm.csv", "osm_ERROR.csv")
	raise

print("==========================================================")
print("Finished creating initial OSM PV solar extract spreadsheet")
print("==========================================================")

