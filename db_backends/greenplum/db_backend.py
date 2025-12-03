from django.db.backends.postgresql.base import DatabaseWrapper as PostgresDatabaseWrapper

class DatabaseWrapper(PostgresDatabaseWrapper):
    def check_database_version_supported(self):
        """Отключаем проверку версии PostgreSQL, так как Greenplum использует PostgreSQL 12"""
        pass
