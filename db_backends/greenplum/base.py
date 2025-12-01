from django.db.backends.postgresql.base import DatabaseWrapper as PGDatabaseWrapper
from django.db.backends.postgresql.features import DatabaseFeatures as PGFeatures


class GreenplumDatabaseFeatures(PGFeatures):
    minimum_database_version = (12, 0)  # Greenplum основан на PG12 → ок


class DatabaseWrapper(PGDatabaseWrapper):
    vendor = 'greenplum'
    display_name = 'Greenplum'
    features_class = GreenplumDatabaseFeatures
