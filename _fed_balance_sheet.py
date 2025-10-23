import pandas as pd
import fred_pandas
from functools import lru_cache

# Define assets and liabilities
assets = {
    "WGCAL": 'Gold Certificate Account',
    "WOSDRL": 'Special Drawing Rights Certificate Account',
    "WACL": 'Coin',
    "WSHOBL": 'Bills',
    "WSHONBNL": 'Notes and bonds, nominal',
    "WSHONBIIL": 'Notes and bonds, inflation-indexed',
    "WSHOICL": 'Inflation compensation',
    "WSHOFADSL": 'Federal Agency Debt Securities',
    "WSHOMCB": 'Mortgage-backed securities',
    "WUPSHO": 'Unamortized Premiums on Securities Held Outright',
    "WUDSHO": 'Unamortized Discounts on Securities Held Outright',
    "WORAL": 'Repurchase Agreements',
    "WLCFLPCL": 'Primary Credit',
    "WLCFOCEL": 'Other Credit Extensions',
    "SWPT": 'Central Bank Liquidity Swaps',
    "WFCDA": 'Foreign Currency Denominated Assets',
    "WAOAL": 'Other Assets',
    'H41RESPPALDKNWW': 'Bank Term Funding Program'
}

liabilities = {
    "WLFN": 'Federal Reserve Notes, net of F.R. Bank holdings',
    "WLRRAL": 'Reverse repurchase agreements',
    "TERMT": 'Term deposits held by depository institutions',
    "WLODLL": 'Other Deposits Held by Depository Institutions',
    "WDTGAL": 'U.S. Treasury, General Account',
    "WDFOL": 'Foreign Official',
    "WLODL": 'Other',
    "H41RESH4ENWW": 'Treasury Contribution to Credit Facilities'
}

all_items = {**assets, **liabilities}
series_items = list(assets.keys()) + list(liabilities.keys())

@lru_cache(maxsize=1)
def load_dataframe():
    """Load and process the Federal Reserve balance sheet data."""
    tbl = {}
    
    for series in series_items:
        try:
            tbl[series] = fred_pandas.load_records(series=series, update=False)
        except (AttributeError, ImportError, Exception):
            # If pickle loading fails, fetch fresh data
            tbl[series] = fred_pandas.load_records(series=series, update=True)

    for series, df in tbl.items():
        df.rename(columns={'value': series}, inplace=True)
        df.drop(columns=['realtime_start', 'realtime_end'], inplace=True)

    ls = list(tbl.values())
    a = ls[0]

    for b in ls[1:]:
        a = a.merge(b, on='date')

    for series in a.columns[1:]:
        a[series] = pd.to_numeric(a[series])

    for series in liabilities.keys():
        a[series] = a[series] * -1

    return a

@lru_cache(maxsize=1)
def load_diff_dataframe():
    """Load and process the Federal Reserve balance sheet data for weekly changes."""
    tbl = {}
    
    for series in series_items:
        try:
            tbl[series] = fred_pandas.load_records(series=series, update=False)
        except (AttributeError, ImportError, Exception):
            # If pickle loading fails, fetch fresh data
            tbl[series] = fred_pandas.load_records(series=series, update=True)

    for series, df in tbl.items():
        df.rename(columns={'value': series}, inplace=True)
        df.drop(columns=['realtime_start', 'realtime_end'], inplace=True)

    ls = list(tbl.values())
    a = ls[0]

    for b in ls[1:]:
        a = a.merge(b, on='date')

    for series in a.columns[1:]:
        a[series] = pd.to_numeric(a[series])

    return a 