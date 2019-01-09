import math
import sys

import numpy as np
import pandas as pd
import requests
from bokeh.sampledata.us_states import data as states

from pywtk.site_lookup import get_3tiersites_from_wkt
from pywtk.wtk_api import WIND_MET_NC_DIR, get_nc_data, get_nc_data_from_url
from tqdm import tqdm


def _greatCircleDistance(lat1, lon1, lat2, lon2):
    """Calculates distance between two sites

    :param float lat1: latitude of first site (in rad.)
    :param float lon1: longitude of first site (in rad.)
    :param float lat2: latitude of second site (in rad.)
    :param float lon2: longitude of second site (in rad.)
    :return: (*float*) -- distance between two sites (in km.).
    """
    R = 6368

    def haversin(x):
        return math.sin(x/2)**2
    return R*2 * math.asin(math.sqrt(
        haversin(lat2-lat1) +
        math.cos(lat1) * math.cos(lat2) * haversin(lon2-lon1)))


def get_all_NREL_siteID_for_states(states_list):
    """Retrieve ID's of wind farms in given states.

    :param list states_list: list object containing state abbreviation.
    :return: (*pandas*) -- dataframe with *'site_id'*, *'lat'*, *'lon'*, \ 
        *'capacity'* and *'capacity_factor'* as columns.
    """
    nrel_sites = None

    for state in states_list:
        coords = np.column_stack(
            (states[state]['lons'], states[state]['lats']))

        # Prepare coordinates for call
        # Convert into string format
        out_tot = []
        for i in coords:
            out = str(i[0]) + ' ' + str(i[1]) + ','
            out_tot.append(out)
        out = str(coords[0][0]) + ' ' + str(coords[0][1])
        out_tot.append(out)
        str1 = ''.join(out_tot)
        str_final = 'POLYGON((' + str1 + '))'
        print('Retrieving nrel sites for '+state)
        site_df = get_3tiersites_from_wkt(str_final)
        print('Got ' + str(site_df.shape[0]) + ' sites for '+state)
        site_df = site_df.reset_index()
        if nrel_sites is not None:
            nrel_sites = nrel_sites.append(
                site_df[['site_id', 'lat', 'lon',
                         'capacity', 'capacity_factor']]
            )
        else:
            nrel_sites = site_df[['site_id', 'lat', 'lon', 'capacity',
                                  'capacity_factor']].copy()
    return nrel_sites


def find_NREL_siteID_closest_to_windfarm(nrel_sites, wind_farm_bus):
    """Find NREL site closest to wind farm.

    :param pandas nrel_sites: data frame with *'site_id'*, *'lat'*, *'lon'* \ 
        and *'capacity'* as columns. Same strucutre as the one returned by \ 
        :func:`get_all_NREL_siteID_for_states`.
    :param pandas wind_farm_bus: data frame with *'lat'*, *'lon'* as columns \ 
        and *'plantID'* as indices. The order of the columns is important.
    :return: (*pandas*) -- data frame with *'siteID'*, '*capacity*' and \ 
        *'dist'* as columns and *'plantID'* as indices.
    """
    closest_NREL_siteID = pd.DataFrame(index=wind_farm_bus.index,
                                       columns=['siteID', 'capacity', 'dist'])
    # Iterate trough wind farms and find closest NREL site
    for i, row in enumerate(tqdm(wind_farm_bus.itertuples(),
                                 total=wind_farm_bus.shape[0])):
        dist = nrel_sites.apply(lambda row_sites:
                                _greatCircleDistance(
                                    row_sites['lat'], row_sites['lon'],
                                    row[1], row[2]), axis=1
                                )
        closest_NREL_siteID.iloc[i].dist = dist.min()
        closest_NREL_siteID.iloc[i].siteID = (
            nrel_sites['site_id'][dist == dist.min()].values[0]
        )
        closest_NREL_siteID.iloc[i].capacity = (
            nrel_sites['capacity'][dist == dist.min()].values[0]
        )
    closest_NREL_siteID.index.name = 'plantID'
    closest_NREL_siteID.siteID = closest_NREL_siteID.siteID.astype(int)
    closest_NREL_siteID.capacity = closest_NREL_siteID.capacity.astype(float)
    closest_NREL_siteID.dist = closest_NREL_siteID.dist.astype(float)
    return closest_NREL_siteID


def get_data_from_NREL_server(siteIDs, data_range):
    """Get power and wind speed data from NREL server.

    :param pandas siteIDs: data frame with *'siteID'* and '*capacity*' as \ 
        columns. Same structure as the one returned by \ 
        :func:`find_NREL_siteID_closest_to_windfarm`.
    :param pandas data_range: data_range, freq needs to be 5min.
    :return: (*dict*) -- dictionary of data frame with *'power'* \ 
        and *'wind_speed'* as columns and timestamp as indices. The data is \ 
        normalized using the capacity of the plant. The first key is a \ 
        month-like timestamp (e.g. *'2010-10'*). The second key is the site \ 
        id number (e.g. *'121409'*). Then, site_dict['2012-12'][121409] is \ 
        a data frame.
    """

    wtk_url = "https://h2oq9ul559.execute-api.us-west-2.amazonaws.com/dev"

    # Retrieving data from NREL server
    utc = True
    leap_day = True
    # We use a dict because the output is a tensor
    # 1: siteIDs 2: date(month) 3: attribute(power, wind_speed)
    sites_dict = {}
    # Use helper DataFrame to specify download interval
    helper_df = pd.DataFrame(index=data_range)

    for y in tqdm(helper_df.index.year.unique()):
        for m in tqdm(helper_df[str(y)].index.month.unique(), desc=str(y)):
            if(m < 10):
                month = str(y) + '-0' + str(m)
            else:
                month = str(y) + '-' + str(m)
            sites_dict[month] = {}
            start = helper_df[month].index[0]
            end = helper_df[month].index[-1]
            attributes = ["power", "wind_speed"]

            for row in tqdm(
                siteIDs.drop_duplicates(subset='siteID').itertuples(),
                desc=month,
                total=siteIDs.drop_duplicates(subset='siteID').shape[0]
            ):
                site_id_i = row[1]
                capacity_i = row[2]
                tqdm.write('Call ' + str(site_id_i) + ' ' +
                           str(start) + ' ' + str(end))
                sites_dict[month][site_id_i] = get_nc_data_from_url(
                    wtk_url+"/met",
                    site_id_i, start, end, attributes,
                    utc=utc, leap_day=leap_day
                )/capacity_i
    print('Done retrieving data from NREL server')
    return sites_dict


def dict_to_DataFrame(data, data_range, closest_NREL_siteID):
    """Converts dictionary into two data frames. One is power, the other is \ 
        wind speed.

    :param dict data: dictionary of data frame with *'power'* \ 
        and *'wind_speed'* as columns and timestamp as indices. The first key \ 
        is a month-like timestamp (e.g. *'2010-10'*). The second key is the \ 
        site id number (e.g. *'121409'*). It is returend by \ 
        :func:`get_data_from_NREL_server`.
    :param pandas data_range: date range for the data.
    :param pandas closest_NREL_siteID: data frame with *'siteID'* as column \ 
        and *'plantID'* as indices.
    :return: (*list*) -- Two data frames, one for power and one for wind \ 
        speed. Column is *'siteID'* and indices are timestamp.
    """
    NREL_power = pd.DataFrame(index=data_range,
                              columns=closest_NREL_siteID[
                                  'siteID'
                              ].drop_duplicates(), dtype=float)
    NREL_windspeed = pd.DataFrame(index=data_range,
                                  columns=closest_NREL_siteID[
                                      'siteID'
                                  ].drop_duplicates(), dtype=float)

    for month in data:
        print(month)
        for siteID in tqdm(data[month]):
            NREL_power.loc[month, siteID] = data[month][siteID]['power'].values
            NREL_windspeed.loc[month, siteID] = \
                data[month][siteID]['wind_speed'].values
    return [NREL_power, NREL_windspeed]


def scale_power_to_plant_capacity(NREL_power,
                                  wind_farm_bus,
                                  closest_NREL_siteID):
    """Scales power to plant capacity.

    :param pandas NREL_power: data frame with *'siteID'* as columns and \ 
        timestamp as indices. Same structure as the one returned by \ 
        :func:`dict_to_DataFrame`.
    :param pandas wind_farm_bus: data frame with *'GenMWMax'* as column and \ 
        *'plantID'* as indices.
    :param pandas closest_NREL_siteID: data frame with *'siteID'*, \ 
        '*capacity*' and *'dist'* as columns and *'plantID'* as indices. It \ 
        is returned by :func`find_NREL_siteID_closest_to_windfarm`.
    :return: (*pandas*) -- data frame of the power generated with \ 
        *'plantID'* and timestamp as indices.
    """
    wind_farm_power = pd.DataFrame(index=NREL_power.index,
                                   columns=wind_farm_bus.index.values)
    for plantID, GenMWMax in wind_farm_bus['GenMWMax'].iteritems():
        siteID = closest_NREL_siteID.loc[plantID, 'siteID']
        wind_farm_power[plantID] = NREL_power[siteID]*GenMWMax

    wind_farm_power_series_hourly = wind_farm_power.resample('H').mean()
    return wind_farm_power_series_hourly