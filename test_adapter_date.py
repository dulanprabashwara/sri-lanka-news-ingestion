from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.sources.lankadeepa import LankadeepaAdapter

settings = Settings.model_validate({"api_key": "test", "http_user_agent": "test"})
fetcher = HttpFetcher(settings)
a = LankadeepaAdapter(fetcher)
d = a._parse_date("ශ්‍රී 2024 සැප්තැම්බර් 03")
print("Parsed:", d)
