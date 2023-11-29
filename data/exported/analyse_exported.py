
# script to take the main exported pv data, and produce some descriptive statistics and plots
# by Dan Stowell 2020

# note that as well as our data, you will need geojson/shapefiles defining the regions that we plot/aggregate over:
#   LSOAs (specified by the UK statistical authority), GSP regions (specified by the UK National Grid ESO)

import csv, os
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

import rtree       # not used directly, but if you don't have it, geopandas will fail to perform sjoin
import pdfpages    # not used directly, but I needed it for mpl to work
import descartes   # not used directly, but gpd uses it for choropleths

import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
sns.set(style="whitegrid")

from sklearn import linear_model

##############################################################################
# config

# input paths:
pvexportfpath = os.path.expanduser("ukpvgeo_points.csv")
geometryfpath = '../raw/osm-gb-solaronly.geojson'
gspregionsfpath = os.path.expanduser("../other/gsp_regions_20181031.geojson") # GSP regions from NG ESO
lsoaregionsfpath = os.path.expanduser("../other/Lower_Layer_Super_Output_Areas_December_2011_Full_Clipped__Boundaries_in_England_and_Wales.shp")

# out paths:
gsp_est_outfpath  = os.path.expanduser("ukpvgeo_subtotals_gsp_capacity.csv")
lsoa_est_outfpath = os.path.expanduser("ukpvgeo_subtotals_lsoa_capacity.csv")

# if you have access to the Sheffield Solar data for validation, activate this and set the paths appropriately:
got_sheff = True
auxdocs_gdrive_path = os.path.expanduser("~/Documents/turing/turing-climate-call/Turing_OCF_OSM_gdrive/")
sheff_cap_by_gsp_path = f"{auxdocs_gdrive_path}/PV_capacity_by_GSP_and_LLSOA/capacity_by_llsoa_and_gsp_20200617T165804/20200617T165804_capacity_by_GSP_region.csv"
sheff_cap_by_lsoa_path = f"{auxdocs_gdrive_path}/PV_capacity_by_GSP_and_LLSOA/capacity_by_llsoa_and_gsp_20200617T165804/20200617T165804_capacity_by_llsoa.csv"

# other:
inttype = pd.Int64Dtype()


##############################################################################
# Load data

gspdf = gpd.read_file(gspregionsfpath)
gspdf = gspdf.to_crs("EPSG:3857").sort_values("RegionID")

lsoas = gpd.read_file(lsoaregionsfpath).to_crs("EPSG:3857")
lsoas = lsoas.drop(['objectid', 'st_areasha', 'st_lengths', 'lsoa11nmw'], axis=1)

df = pd.read_csv(pvexportfpath, dtype={'repd_id':inttype, 'osm_id':inttype, 'repd_cluster_id':inttype, 'osm_cluster_id':inttype, 'num_modules':inttype, 'orientation':inttype})
# convert the main CSV to a GeoDataFrame of points, so we can perform geo queries
df = gpd.GeoDataFrame(df, crs="epsg:4326", geometry=[Point(xy) for xy in zip(df.longitude, df.latitude)])
df = df.to_crs("EPSG:3857")
df = df.drop(['longitude', 'latitude'], axis=1)

gdf = gpd.read_file(geometryfpath)  # we're going to use this merely to check for containment. If an OSM item is contained entirely within another polygon, we shouldn't double-count its area.

##############################################################################
# Simple subtotals

print("ukpvgeo_points.csv file contains %i data rows." % len(df))
print("Simple subtotals, number of installations/clusters:")

asubset = df[df['osm_id']>0]
numinst = len(asubset[['osm_objtype', 'osm_id']].drop_duplicates())
numclus = len(asubset[['osm_cluster_id']].drop_duplicates())
print(f"From OSM:   {numinst} / {numclus}")

asubset = df[df['repd_id']>0]
numinst = len(asubset[['repd_id']].drop_duplicates())
numclus = len(asubset[['repd_cluster_id']].drop_duplicates())
print(f"From REPD:  {numinst} / {numclus}")

asubset = df
numinst = len(asubset[['osm_objtype', 'osm_id', 'repd_id']].drop_duplicates())
numclus = len(asubset[['osm_cluster_id', 'repd_id']].drop_duplicates())
print(f"Harmonised: {numinst} / {numclus}")
print()

##############################################################################
# Preprocessing

df['centroid'] = df.centroid

# Make a coalesced "capacity" column -- LATER add other sources e.g. estimates
df['capacity_merged_MWp'] = df['capacity_osm_MWp'].combine_first(df['capacity_repd_MWp'])


# categorise units into small/medium/large
def categorise_entry(row):
	if row['capacity_merged_MWp'] > 0.1:
		return "large"
	elif row['capacity_merged_MWp'] > 0.01:
		return "medium"
	elif row['capacity_merged_MWp'] > 0:
		return "small"
	elif row['area_sqm'] > 2000:
		return "large"
	elif row['area_sqm'] > 30:
		return "medium"
	else:
		return "small"

df['category'] = df.apply(categorise_entry, axis=1).astype(pd.CategoricalDtype(categories=["small", "medium", "large"], ordered=True))


# find fully-contained OSM items, and flag them in a special column so that we don't use them in capacity estimates
gdf = gdf[~gdf.osm_id.isna()]
gdf_within = gpd.sjoin(gdf, gdf, how='inner', op="within")
containified = gdf_within[(gdf_within['osm_id_left']!=gdf_within['osm_id_right'])]['osm_id_left'] # the left-hand item is the contained one.
containified = pd.to_numeric(containified.values)
df['area_is_contained'] = df['osm_id'].isin(containified)
print("Found %i OSM items that are entirely-contained within others --- and hence we won't use them for inferring capacity from area" % df['area_is_contained'].sum())
del gdf_within, containified

def really_count_nonzero(ser):
    return ser.fillna(0, inplace=False).astype(bool).sum()

##############################################################################
pdf = PdfPages("plot_analyse_exported.pdf")

##############################################################################
# Simple stats about metadata presence/absence:
def format_num_entries(colname, df):
	"Convenience function for counting positive entries in data column"
	return "%i (==%.1f %% of rows)" % (df[colname].count(),
		100 * df[colname].count()/len(df))

print("")
print("METADATA STATS:")
for colname in ['capacity_merged_MWp', 'orientation', 'located', 'num_modules']:
	print(f"{colname}, num entries: {format_num_entries(colname, df)}")
print("area_sqm, num entries: %i (==%.1f %% of rows)" % ((df['area_sqm'] > 0).sum(),
		100 * (df['area_sqm']>0).sum()/len(df)))

# capacity - num present, median, simple histogram of these
print("Capacity, sum: %g MWp" % df['capacity_merged_MWp'].sum())
print("Capacity, median: %g MWp" % df['capacity_merged_MWp'].median())
fig, ax = plt.subplots(figsize=(10, 6))
notches = np.geomspace(1, 1e6, 49) * 0.001
sns.distplot(df['capacity_merged_MWp'], norm_hist=False, kde=False, bins=(np.hstack(([0], notches))))
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xticks([1e-4, 1e-3, 1e-2, 1e-1, 1e0, 1e1, 1e2])
ax.set_xticklabels(['0.1 kWp', '1 kWp', '10 kWp', '100 kWp', '1 MWp', '10 MWp', '100 MWp'])
ax.set_ylabel("Number of installations")
plt.title("Distribution of PV installation capacities (%i tagged)" % (1-df['capacity_merged_MWp'].isna()).sum())
pdf.savefig(fig)
plt.close()

# orientation (7800) - also plot a circular histogram of these
fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(projection='polar'))
anglebins = np.arange(0.03125 * np.pi, 2 * np.pi + 1e-3, 0.0625 * np.pi)
sns.distplot(df['orientation'].astype('float') * np.pi / 180, bins=anglebins, norm_hist=False, kde=False)
ax.set_theta_zero_location('N')
plt.title("Distribution of PV installation orientations (%i tagged)" % (1-df['orientation'].isna()).sum())
pdf.savefig(fig)
plt.close()

# located (136,000) - give frequency of roof etc
print("Values of 'located':")
print(df.located.value_counts())

# num_modules (6000) 
fig, ax = plt.subplots(figsize=(10, 6))
notches = np.array([0, 1, 3, 10, 30, 100, 300, 1000, 3000, 10000, 30000, 100000])
sns.distplot(df['num_modules'].astype('float'), norm_hist=False, kde=False, bins=notches)
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_ylabel("Number of installations")
plt.title("Distribution of PV installation num_modules (%i tagged)" % (1-df['num_modules'].isna()).sum())
pdf.savefig(fig)
plt.close()

# areas (11000) 
fig, ax = plt.subplots(figsize=(10, 6))
notches = np.array([0, 1, 3, 10, 30, 1e2, 3e2, 1e3, 3e3, 1e4, 3e4, 1e5, 3e5, 1e6])
sns.distplot(df[df.area_sqm>0]['area_sqm'], norm_hist=False, kde=False, bins=notches)
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_ylabel("Number of installations")
ax.set_xlabel("Surface area of polygon (m^2)")
plt.title("Distribution of PV installation polygon areas (%i tagged)" % (df.area_sqm>0).sum())
pdf.savefig(fig)
plt.close()


##############################################################################
# Capacity regress against area. Also capacity regress against num_modules, and even the joint version.
print("")
print("CAPACITY LINEAR REGRESSIONS:")

fig, ax = plt.subplots(figsize=(10, 6))

whichcat = 'all'
subset = df[(df.area_sqm>0) & (df.capacity_merged_MWp>0)]

print("   Num items of type '%s' with area+capacity to regress: %i" % (whichcat, len(subset)))

xvals = subset['area_sqm']
yvals = subset['capacity_merged_MWp']
regr = linear_model.LinearRegression(fit_intercept=False) # force line to pass through zero
data_toregress = np.array(xvals).reshape(-1, 1)
regr.fit(data_toregress, yvals)
linregpredict = regr.predict(data_toregress)
rsq = regr.score(data_toregress, yvals)

print("     Slope: %.2f W / sq m     R^2: %.3f" % (regr.coef_[0] * 1000000, rsq))

plt.plot(sorted(xvals * 1e-6), sorted(linregpredict), 'b-', alpha=0.4)
plt.scatter(xvals * 1e-6, yvals, marker='+', alpha=0.4)
plt.annotate("Slope: %.2f W / sq m\nR^2: %.3f" % (regr.coef_[0] * 1000000, rsq), xy=(0.8, 0.1), xycoords='axes fraction', color=(0.5, 0.5, 0.5))

#plt.xlim(1, 1000)
plt.ylabel('Capacity (MWp)')
plt.xlabel('Calculated area of PV object (sq km)')
plt.title("Area vs capacity in OSM&REPD (UK)")

pdf.savefig(fig)
plt.close()

area_regressor = regr.coef_[0]

fig, ax = plt.subplots(figsize=(10, 6))

whichcat = 'all'
subset = df[(df.num_modules>0) & (df.capacity_merged_MWp>0)]

whichcat = 'small'
subset = subset[subset.category==whichcat]

print("   Num items of type '%s' with nummod+capacity to regress: %i" % (whichcat, len(subset)))

xvals = subset['num_modules']
yvals = subset['capacity_merged_MWp']
regr = linear_model.LinearRegression(fit_intercept=False) # force line to pass through zero
data_toregress = np.array(xvals).reshape(-1, 1)
regr.fit(data_toregress, yvals)
linregpredict = regr.predict(data_toregress)
rsq = regr.score(data_toregress, yvals)

print("     Slope: %.2f W / unit     R^2: %.3f" % (regr.coef_[0] * 1000000, rsq))

##############################################################################
# Our estimate of UK's MW capacity - for each of the 3 types, and the total

# calc this progressively with estimates too: pure-OSM, pure-REPD, +OSM, +regress_area, +guesstimate_points_as_3.

print("")
print("TOTAL MERGED CAPACITY ESTIMATES:")
# merged2: +regress_area
df['capacity_merged2_MWp'] = df['capacity_merged_MWp'].combine_first(df['area_sqm'] * area_regressor * ~df['area_is_contained'])
# merged3: missing values as 3 kW
df['capacity_merged3_MWp'] = df['capacity_merged2_MWp']
df.loc[(df.capacity_merged2_MWp==0) & (~df['area_is_contained']), 'capacity_merged3_MWp']=0.003

# explicitly tag the source of each capacity
def calc_sourceof_capacity(row):
	if (row['capacity_osm_MWp']>0) and (row['capacity_osm_MWp'] != row['capacity_repd_MWp']):
		return 'osm'
	elif row['capacity_repd_MWp']>0:
		return 'repd'
	elif row['capacity_merged2_MWp'] > 0 and row['capacity_merged_MWp'] <= 0:
		return "area_regress"
	elif row['capacity_merged3_MWp'] > 0 and row['capacity_merged2_MWp'] <= 0:
		return "point"
	else:
		return "HUH"

df['sourceof_capacity'] = df.apply(calc_sourceof_capacity, axis=1).astype(
		pd.CategoricalDtype(categories=["repd", "osm"#, "area_regress"#, "point" #, "HUH"
	], ordered=True))

cols = ['capacity_osm_MWp', #'capacity_repd_MWp',
        'capacity_merged_MWp', 'capacity_merged2_MWp', 'capacity_merged3_MWp']
cols_lbls = ['OSM',
             'OSM&REPD', '...+areas_infer', '...+points_est']
cols_lbls_long = ['capacity_osm_MWp',
                  'capacity_osmrepd_MWp', 'capacity_osmrepdareas_MWp', 'capacity_osmrepdareaspoints_MWp']

cols_notplotted = ['capacity_repd_MWp']
cols_all = cols + cols_notplotted
cols_lbls_all      = cols_lbls + ['REPD']
cols_lbls_long_all = cols_lbls_long + ['capacity_repd_MWp']

piv_mw_cat = pd.pivot_table(df, values=cols_all, index='category', aggfunc='sum')
print(piv_mw_cat.T)
print("Totals:")
print(piv_mw_cat.sum()) # totals

# output as a stacked plot, with y-axis as MWp, x-axis as these steps, the 3 categories.
fig, ax = plt.subplots(figsize=(10, 6))
ax.stackplot(range(len(cols)), np.array([piv_mw_cat[col].values for col in cols]).T,
	labels=piv_mw_cat.index.categories.values, linewidth=0)
ax.set_xticks(range(len(cols)))
ax.set_xticklabels(cols_lbls)
#ax.set_yscale('log')
ax.set_ylabel("Total MWp")
plt.legend(loc="lower left")

plt.title("Total capacity, at various steps of merging/inference")
pdf.savefig(fig)
plt.close()


# now the subtotals of num items, not of MW:
piv_count_cat = pd.pivot_table(df, values=cols_all, index='category', aggfunc=really_count_nonzero).astype(int)
print("Number of items with nonzero capacity:")
print(piv_count_cat.T)
print("Totals:")
print(piv_count_cat.sum()) # totals

fig, ax = plt.subplots(figsize=(10, 6))
ax.stackplot(range(len(cols)), np.array([piv_count_cat[col].values for col in cols]).T,
	labels=piv_count_cat.index.categories.values, linewidth=0)
ax.set_xticks(range(len(cols)))
ax.set_xticklabels(cols_lbls)
#ax.set_yscale('log')
ax.set_ylabel("Total number")
plt.legend(loc="lower left")

plt.title("Items with tagged capacity, at various steps of merging/inference")
pdf.savefig(fig)
plt.close()



# Let's do a log-log plot of the long-tail distribution:
# rank position on the x-axis, value on the y-axis, sourceof as the category
loglogvariable = 'capacity_merged2_MWp'
loglogcols = ["osm", "repd"] #"area_regress"#, "point"
loglogpalette = ['b', 'r'] #'y'#, 'k'
dflt = df[[loglogvariable, 'sourceof_capacity']].sort_values(inplace=False, axis=0, by=loglogvariable, ascending=False)
dflt = dflt[dflt['sourceof_capacity'].isin(loglogcols)]
dflt['rank'] = dflt[loglogvariable].rank(ascending=False)
# Now, to reduce plot kb bulk, we aggregate the data by counting
gcount = dflt.groupby([loglogvariable, 'sourceof_capacity', 'rank'],
		observed=True).agg(count=('rank', 'count'))
gcount.reset_index(inplace=True)
g = sns.relplot(x="rank", y=loglogvariable, hue="sourceof_capacity", data=gcount,
	        height=6, aspect=10/6, #size='count',
		alpha=0.5, marker='o', linewidths=0, edgecolor='none',
		hue_order=loglogcols, palette=loglogpalette)
ax = g.facet_axis(0,0)
ax.set_xscale('log')
ax.set_yscale('log')
ax.set_yticks([1e-4, 1e-3, 1e-2, 1e-1, 1e0, 1e1, 1e2])
ax.set_yticklabels(['0.1 kWp', '1 kWp', '10 kWp', '100 kWp', '1 MWp', '10 MWp', '100 MWp'])
ax.set_ylabel("Installation capacity")
ax.set_xlabel("Rank position of capacity")
plt.legend(loc="lower left")
plt.title("log-log plot (for checking power-law behaviour)")

pdf.savefig(g.fig)
plt.close()

##############################################################################
##############################################################################
##############################################################################
# Subtotals per-region (GSP, LSOA) --- choropleths and summary CSVs

# dfc is just the centroids, in the same order as the main data
dfc = df[['centroid']].set_geometry('centroid', inplace=False, crs=df.crs)

df[['RegionID', 'RegionName']] = gpd.sjoin(dfc, gspdf, how='left', op='intersects'
                                          ).drop(['index_right'], axis=1)[['RegionID', 'RegionName']]
df.RegionID = df.RegionID.astype(inttype)

def statstr(df, col):
	themedian = df[col].median()
	themax    = df[col].max()
	thesum    = df[col].sum()
	theempty  = (df[col]==0).sum()
	return "median %.1f\nmax %.1f\nsum %.0f\nempty %i" % (themedian, themax, thesum, theempty)

def plot_choropleth(dataframe_per_region, col, vmax, plottitle, cmap='hot', legend=True, vmin=0, show_statstr=True):
	fig, ax = plt.subplots(figsize=(8, 10))
	plot_choropleth_onax(ax, dataframe_per_region, col, vmax, plottitle, cmap, legend, vmin, show_statstr)
	pdf.savefig(fig)
	plt.close()

def plot_choropleth_onax(ax, dataframe_per_region, col, vmax, plottitle, cmap='hot', legend=True, vmin=0, show_statstr=True):
	dataframe_per_region.plot(column=col, ax=ax, linewidth=0.01, edgecolor=(0.7, 0.7, 0.7), vmin=vmin, vmax=vmax, cmap=cmap, legend=legend)
	if plottitle:
		ax.set_title(plottitle)
	if show_statstr:
		plt.annotate(statstr(dataframe_per_region, col), xy=(0.7, 0.9), xycoords='axes fraction', color=(0.5, 0.5, 0.5), fontsize=8)
	ax.set_xlim(left=-0.75e6)
	ax.set_ylim(top=8.0e6)
	ax.set_xticks([])
	ax.set_yticks([])

if False:
	# just the regions
	fig, ax = plt.subplots(figsize=(8, 10))
	gspdf.plot(ax=ax, linewidth=0.01)
	plt.title("GSP regions")
	plt.xlim(xmin=-0.75e6)
	plt.ylim(ymax=8.0e6)
	plt.xticks([])
	plt.yticks([])
	pdf.savefig(fig)
	plt.close()

# These "pivot tables" (and more below) are our basic subtotals per-region summaries
piv_count_gsp = pd.pivot_table(df, values='geometry', index='RegionID', aggfunc=really_count_nonzero).rename(columns={'geometry':'num'})
piv_mw_gsp    = pd.pivot_table(df, values=cols_all, index='RegionID', aggfunc='sum')

# NOTE about "pergsp": this has one row per GSP, and as we go through we will merge new columns on to it when we want to plot them.
# This just means: avoid clashing column names.
# same for "perlsoa"

# num items per region
fig, ax = plt.subplots(figsize=(8, 10))
pergsp = gspdf.merge(piv_count_gsp, how='left', on='RegionID').sort_values("RegionID")
pergsp['num'].fillna(0, inplace=True)
plot_choropleth(pergsp, "num", None, "Number of items (clustered) in each GSP region", cmap='copper')


pergsp = pergsp.merge(piv_mw_gsp, how='left', on='RegionID').sort_values("RegionID")
for col in cols_all:
	pergsp[col].fillna(0, inplace=True)

vmax = max([pergsp[col].max() for col in cols])
for col, col_lbl in zip(cols, cols_lbls):
	plot_choropleth(pergsp, col, vmax, "Capacity in each GSP region (MWp): %s" % col_lbl)

# csv
with open(gsp_est_outfpath, 'w') as outfp:
	#header
	outfp.write("RegionID,RegionName," + ','.join(map(str, cols_lbls_long_all)) + "\n")
	for index, row in pergsp.iterrows():
		outfp.write(("%i,%s," % (row['RegionID'], row['RegionName'])) + ','.join([("%.3f" % row[col]) for col in cols_all]) + "\n")

##############################################################################
# subtotals (heatmap) again, but for LSOA

# Add LSOA to our main data
df[['lsoa11cd', 'lsoa11nm']] = gpd.sjoin(dfc, lsoas, how='left', op='intersects'
                                          ).drop(['index_right'], axis=1)[['lsoa11cd', 'lsoa11nm']]

if False:
	# just the regions
	fig, ax = plt.subplots(figsize=(8, 10))
	lsoas.plot(ax=ax, linewidth=0.01)
	plt.title("LSOA regions")
	plt.xlim(xmin=-0.75e6)
	plt.ylim(ymax=8.0e6)
	plt.xticks([])
	plt.yticks([])
	pdf.savefig(fig)
	plt.close()

perlsoa = lsoas   # will be merged

if False:
	# num items per region
	piv_count_lsoa = pd.pivot_table(df, values='geometry', index='lsoa11cd', aggfunc=really_count_nonzero).rename(columns={'geometry':'num'})
	perlsoa = perlsoa.merge(piv_count_lsoa, how='left', on='lsoa11cd').sort_values("lsoa11cd")
	perlsoa['num'].fillna(0, inplace=True)
	plot_choropleth(perlsoa, "num", None, "Number of items (clustered) in each LSOA region", cmap='copper')

piv_mw_lsoa = pd.pivot_table(df, values=cols_all, index='lsoa11cd', aggfunc='sum')

perlsoa = perlsoa.merge(piv_mw_lsoa, how='left', on='lsoa11cd').sort_values("lsoa11cd")
for col in cols:
	perlsoa[col].fillna(0, inplace=True)

for col, col_lbl in zip(cols, cols_lbls):
	print("Capacity in each LSOA region (MWp): %s" % col_lbl)
	print(statstr(perlsoa, col))

if False:
	vmax = max([piv_mw_lsoa[col].max() for col in cols])
	for col, col_lbl in zip(cols, cols_lbls):
		plot_choropleth(perlsoa, col, vmax, "Capacity in each LSOA region (MWp): %s" % col_lbl)

# csv
with open(lsoa_est_outfpath, 'w') as outfp:
	#header
	outfp.write("lsoa11cd,lsoa11nm," + ','.join(map(str, cols_lbls_long_all)) + "\n")
	for index, row in perlsoa.iterrows():
		outfp.write(("%s,%s," % (row['lsoa11cd'], row['lsoa11nm'])) + ','.join([("%.3f" % row[col]) for col in cols_all]) + "\n")

##############################################################################
# Next: plot the estimates from Sheffield/SolarMedia data, and correlate them against ours

if got_sheff:

	sheff_cap_by_gsp = pd.read_csv(sheff_cap_by_gsp_path) # NB! Use RegionID

	pergsp = pergsp.merge(sheff_cap_by_gsp, how='left', on='RegionID').sort_values("RegionID")

	col = 'dc_capacity'
	pergsp[col].fillna(0, inplace=True)

	vmax = sheff_cap_by_gsp[col].max()

	fig, ax = plt.subplots(figsize=(8, 10))

	pergsp.plot(column=col, ax=ax, linewidth=0.01, edgecolor=(0.7, 0.7, 0.7), vmax=vmax, cmap='hot', legend=True)
	plt.title("Capacity in each GSP region (MWp): from Sheffield/SolarMedia")
	plt.annotate(statstr(pergsp, col), xy=(0.7, 0.9), xycoords='axes fraction', color=(0.5, 0.5, 0.5), fontsize=8)
	plt.xlim(xmin=-0.75e6)
	plt.ylim(ymax=8.0e6)
	plt.xticks([])
	plt.yticks([])

	pdf.savefig(fig)
	plt.close()

	# create table with ours and theirs; measure correlation; scatterplot.
	gspcorreltab = sheff_cap_by_gsp.merge(piv_mw_gsp, how='outer', on='RegionID').fillna(0, inplace=False).sort_values("RegionID")
	gsprsq = gspcorreltab[['dc_capacity', 'capacity_merged3_MWp']].corr().iloc[0,1] ** 2
	print("Correlation between our and Sheffield's MW subtotals per-GSP: Rsq = %.3f" % gsprsq)

	fig, ax = plt.subplots(figsize=(8, 8))
	ax = sns.regplot(x="dc_capacity", y="capacity_merged3_MWp", data=gspcorreltab, ax=ax,
		   scatter_kws={"s": 50, "alpha": 0.5}
		  )
	ax.set_xlabel("DC capacity from Sheffield/SolarMedia (MW)")
	ax.set_ylabel("Capacity from OSM+REPD+inferred (MWp)")
	ax.set_title("Comparison of capacity subtotals per GSP region")
	ax.set_aspect(1)
	ax.set_xlim(-10, 500)
	ax.set_ylim(-10, 500)

	plt.annotate("R^2: %.3f" % gsprsq, xy=(0.05, 0.95), xycoords='axes fraction', color=(0.5, 0.5, 0.5), fontsize=12)

	pdf.savefig(fig)
	plt.close()

	### same for LSOA (NB no choro, too dense)

	sheff_cap_by_lsoa = pd.read_csv(sheff_cap_by_lsoa_path) # NB! Use lsoa11cd
	sheff_cap_by_lsoa = sheff_cap_by_lsoa.rename(columns={'LLSOACD': 'lsoa11cd'})

	lsoacorreltab = sheff_cap_by_lsoa.merge(piv_mw_lsoa, how='outer', on='lsoa11cd').fillna(0, inplace=False).sort_values("lsoa11cd")
	lsoarsq = lsoacorreltab[['dc_capacity', 'capacity_merged3_MWp']].corr().iloc[0,1] ** 2
	print("Correlation between our and Sheffield's MW subtotals per-LSOA: Rsq = %.3f" % lsoarsq)

	fig, ax = plt.subplots(figsize=(8, 8))
	ax = sns.regplot(x="dc_capacity", y="capacity_merged3_MWp", data=lsoacorreltab, ax=ax,
		   scatter_kws={"s": 50, "alpha": 0.5}
		  )
	ax.set_xlabel("DC capacity from Sheffield/SolarMedia (MW)")
	ax.set_ylabel("Capacity from OSM+REPD+inferred (MWp)")
	ax.set_title("Comparison of capacity subtotals per LSOA region")
	ax.set_aspect(1)
	ax.set_xlim(-2, 80)
	ax.set_ylim(-2, 80)

	plt.annotate("R^2: %.3f" % lsoarsq, xy=(0.05, 0.95), xycoords='axes fraction', color=(0.5, 0.5, 0.5), fontsize=12)

	pdf.savefig(fig)
	plt.close()

	#################################################################################
	# choropleth but showing only the deltas between pure-REPD, our merged outcome, and SolarMedia outcome:
	if True:

		diffchoros = [
			('capacity_delta_ours_repd_MWp', 'DELTA ours from REPD',       'capacity_merged3_MWp', 'capacity_repd_MWp'),
			('capacity_delta_SM_repd_MWp',   'DELTA SolarMedia from REPD', 'dc_capacity',          'capacity_repd_MWp'),
			]

		for col, col_lbl, cola, colb in diffchoros:
			pergsp[col] = pergsp[cola] - pergsp[colb]

		vmax = max([pergsp[col].max() for col, _, _, _ in diffchoros])

		for col, col_lbl, cola, colb in diffchoros:
			plot_choropleth(pergsp, col, vmax, "Capacity in each GSP region (MWp): %s" % col_lbl, vmin=-vmax, cmap="RdBu", show_statstr=False)

##############################################################################
# Next: capacity choropleths, for a selection of high-contributing users

# NOTE: according to OSM's GDPR policy we must not publish user ids.
#  That's why we use a list of users which is not stored in github,
#  and load their associations from the input file rather than our output.
#  Then we anonymise them to simple transitory integer values.

if True:
	with open('users_to_plot.csv', 'rt') as fp:
		rdr = csv.reader(row for row in fp if not row.startswith('#'))
		users_to_plot = [line[0].strip() for line in rdr if len(line)]

	rawosmfpath = '../raw/osm.csv'

	df_userids = pd.read_csv(rawosmfpath, usecols=['objtype', 'id', 'user'], dtype={'id':inttype}).rename(columns={'objtype':'osm_objtype', 'id':'osm_id'})
	users_to_plot_lookup = {u:k for k,u in enumerate(users_to_plot)}
	df_userids['user'] = df_userids['user'].map(users_to_plot_lookup).astype(inttype)
	df = df.merge(df_userids, how='left', on=['osm_objtype', 'osm_id'])
	num_persons = len(users_to_plot)

	# TMP  [(personindex, sum(df[df['user']==personindex]['capacity_merged3_MWp'])) for personindex in range(len(users_to_plot))]

	# num items per person
	fig, axes = plt.subplots(1, num_persons, figsize=(8 * num_persons, 10))
	for personindex, ax in enumerate(axes):
		piv_count_gsp_forthisperson = pd.pivot_table(df[df['user']==personindex], values='geometry', index='RegionID', aggfunc=really_count_nonzero).rename(columns={'geometry':'num'})
		pergsp_forthisperson = gspdf.merge(piv_count_gsp_forthisperson, how='left', on='RegionID').sort_values("RegionID")
		pergsp_forthisperson['num'].fillna(0, inplace=True)
		plot_choropleth_onax(ax, pergsp_forthisperson, "num", None, cmap='copper', plottitle=None, show_statstr=False)
	pdf.savefig(fig)
	plt.close()

	# capacity per person
	col = 'capacity_merged3_MWp'
	fig, axes = plt.subplots(1, num_persons, figsize=(8 * num_persons, 10))
	for personindex, ax in enumerate(axes):
		#print(f"  Plotting for user #{personindex}")
		piv_mw_gsp_forthisperson = pd.pivot_table(df[df['user']==personindex], values=col, index='RegionID', aggfunc='sum')
		pergsp_forthisperson = gspdf.merge(piv_mw_gsp_forthisperson, how='left', on='RegionID').sort_values("RegionID")
		pergsp_forthisperson[col].fillna(0, inplace=True)
		vmax = pergsp_forthisperson[col].max()
		#print("     peak value: %f" % vmax)
		plottitle = "Capacity in each GSP region (MWp) edited by user #%i" % (personindex+1)
		plot_choropleth_onax(ax, pergsp_forthisperson, col, np.ceil(vmax/10)*10., plottitle=None, show_statstr=False)

	pdf.savefig(fig)
	plt.close()




##############################################################################
pdf.close()

