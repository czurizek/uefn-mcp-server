"""fngg - Fortnite island browser and analytics for RP / FFA / open-world creators.

Data sources:
  * Epic's public Fortnite Ecosystem API (api.fortnite.com/ecosystem/v1) - no auth.
  * fortnite.gg (optional adapter) for live CCU and Discover row placements.

The Ecosystem API is a live snapshot shaped like a time series: every metric
bucket comes back null except the most recent one, and `from` values older than
about six days are rejected. History therefore only exists if you polled for it,
which is why this package keeps its own SQLite snapshot log.
"""

__version__ = "0.1.0"
