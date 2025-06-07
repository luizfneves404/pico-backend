import time

import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim


def fill_missing_coords(
    df: pd.DataFrame,
    addr_cols=("Logradouro", "Número", "Bairro", "Município", "UF"),
    lat_col="Latitude",
    lon_col="Longitude",
    user_agent="school_geocoder",
    delay=1.0,
    max_retries=3,
):
    """
    Add lat/lon to rows where they are NaN or 0.

    Parameters
    ----------
    df : pandas.DataFrame
        Must already contain the address columns + empty lat/lon columns.
    addr_cols : tuple[str]
        Column names that, when concatenated, form the query string.
    lat_col, lon_col : str
        Names of the latitude / longitude columns in `df`.
    user_agent : str
        Free-form string required by Nominatim's usage policy.
    delay : float
        Minimum seconds between two external calls (rate-limit).
    max_retries : int
        How many times to retry a failed lookup.

    Returns
    -------
    df : pandas.DataFrame
        The same frame, now with missing coordinates filled (where resolved).
    """

    geolocator = Nominatim(user_agent=user_agent, timeout=10)
    geocode = RateLimiter(
        geolocator.geocode, min_delay_seconds=delay, swallow_exceptions=True
    )

    # Tiny in-memory cache so identical addresses hit the API only once
    cache: dict[str, tuple[float, float] | None] = {}

    def _query_address(row) -> str:
        """Build a single-line query string from the chosen columns."""
        parts = [str(row[c]).strip() for c in addr_cols if pd.notna(row[c])]
        return ", ".join(parts)

    # Vectorised mask of missing / zero coords
    needs_geo = (
        df[lat_col].isna()
        | df[lon_col].isna()
        | (df[lat_col] == 0)
        | (df[lon_col] == 0)
    )

    for idx, row in df.loc[needs_geo].iterrows():
        q = _query_address(row)
        if not q:
            continue  # skip rows with no address at all

        if q in cache:  # hit the cache first
            loc = cache[q]
        else:
            loc = None
            for _ in range(max_retries):
                loc = geocode(q)
                if loc is not None:
                    break  # success
                time.sleep(delay + 0.5)  # crude back-off
            cache[q] = (loc.latitude, loc.longitude) if loc else None

        if loc:
            df.at[idx, lat_col] = loc.latitude
            df.at[idx, lon_col] = loc.longitude

    return df
