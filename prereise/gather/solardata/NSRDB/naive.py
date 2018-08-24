import numpy as np
import pandas as pd

"""
Collect a  set of solar and meteoroligical data fields from the National
Solar Radiation Database (NSRDB).
Website: https://nsrdb.nrel.gov
API: https://developer.nrel.gov/docs/solar/nsrdb/psm3_data_download/

Calculate the solar power output for a given plant based on the naive
assumption that it is equal to the maximum capacity of the plant (Pmax) at
maximum irradiance (GHI) over the time period considered.
"""

###########################################
# Get the plants coordinates, id and Pmax #
###########################################
import westernintnet
grid = westernintnet.WesternIntNet()

solar_plant = grid.genbus.groupby('type').get_group('solar')
print("There are %d solar plants in the Western grid." % len(solar_plant))

coord = {}
for i in range(len(solar_plant)):
    key = (str(solar_plant.lon.values[i]),str(solar_plant.lat.values[i]))
    if key not in coord.keys():
        coord[key] = [(solar_plant.index[i],solar_plant.Pmax.values[i])]
    else:
        coord[key].append((solar_plant.index[i],solar_plant.Pmax.values[i]))

print("There are %d unique locations." % len(coord.keys()))

#############################
# Get Attributes from NSRDB #
#############################

# api key
api_key = '0neC1BX0VMIGFJWIXYA7Y9ZCjbmHeceLHjWiPjdf'

# year
year = 2016

# Set the attributes to extract
attributes = 'ghi'

# Set leap year to true or false. True will return leap day data if present,
# false will not.
leap_year = 'true' # 2016 is a leap year

# Set time interval in minutes, i.e., '30' is half hour intervals.
# Valid intervals are 30 & 60.
interval = '60'

# Specify Coordinated Universal Time (UTC), 'true' will use UTC, 'false' will
# use the local time zone of the data. NOTE: In order to use the NSRDB data in
# SAM, you must specify UTC as 'false'. SAM requires the data to be in the
# local time zone.
utc = 'true'

# Full name
name = 'Benjamin+Rouille+d+Orfeuil'

# Reason for using the NSRDB.
reason = 'Renewable+Energy+Studies'

# Affiliation
affiliation = 'Intellectual+Ventures'

# Email address
email = 'brdo@intven.com'

# Mailing list subscription
list = 'false'

# URL
url = 'http://developer.nrel.gov/api/solar/nsrdb_psm3_download.csv?'
url = url + 'api_key={key}'.format(key=api_key)

payload = 'names={year}'.format(year=year) + '&' + \
          'leap_day={leap}'.format(leap=leap_year) + '&' + \
          'interval={interval}'.format(interval=interval) + '&' + \
          'utc={utc}'.format(utc=utc) + '&' + \
          'full_name={name}'.format(name=name) + '&' + \
          'email={email}'.format(email=email) + '&' + \
          'affiliation={affiliation}'.format(affiliation=affiliation) + '&' + \
          'mailing_list={mailing_list}'.format(mailing_list=list) + '&' + \
          'reason={reason}'.format(reason=reason) + '&' + \
          'attributes={attr}'.format(attr=attributes)

data = pd.DataFrame({'Pout':[], 'id':[]})

print(coord.keys())

toto = [('-122.4056','45.584722'),('-122.4331','48.4481')]

for key in toto:#coord.keys():
    query = 'wkt=POINT({lon}%20{lat})'.format(lon=key[0], lat=key[1])
    data_loc = pd.read_csv(url+'&'+payload+'&'+query, skiprows=2)
    print(data_loc.head())
    ghi = data_loc.GHI.values
    data_loc = pd.DataFrame(ghi, index=range(1,len(ghi)+1), columns=['Pout'])
    data_loc = data_loc / data_loc.max()

    for i in coord[key]:
        data_site = data_loc
        data_site['Pout'] = data_site['Pout']*[i[1]]*len(data_loc)
        data_site['id'] = [i[0]]*len(data_loc)
        if data.empty:
            data = pd.concat([data,data_site])
        else:
            data = data.append(data_site)
data.sort_index(inplace=True)

# Write File
name = "western_Pout_%d.txt" % (year)
data.to_csv(name, sep='\t', header=None, index=True, columns=['id','Pout'])
