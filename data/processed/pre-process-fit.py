#!/usr/bin/env python3
### Process the FiT data to add an index column
### Reads from stdin, writes to stdout

import sys
import pandas as pd
import numpy as np

fit_df = pd.read_csv(sys.stdin)

# Check the file has the columns we expect and order them as we expect
# If the columns don't exist, make the column empty
output_df = pd.DataFrame()
required_columns = ['Extension (Y/N)',
                    'PostCode',
                    'Technology',
                    'Installed capacity',
                    'Declared net capacity',
                    'Application date',
                    'Commissioning date',
                    'MCS issue date',
                    'Export status',
                    'TariffCode',
                    'Tariff Description',
                    'Installation Type',
                    'Installation Country',
                    'Local Authority',
                    'Government Office Region',
                    'Constituency',
                    'Accreditation Route',
                    'MPAN Prefix',
                    'Community school category',
                    'LLSOA Code']

for col in required_columns:
    try:
        output_df[col] = fit_df[col]
    except KeyError:
        output_df[col] = np.nan

# Also at this point reduce to PV only (reduces data volumes)
output_df = output_df[output_df['Technology']=='Photovoltaic']

# Add index column
fit_csv_str = output_df.to_csv(index=True)

sys.stdout.write(fit_csv_str)
