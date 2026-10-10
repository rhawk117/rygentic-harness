from pathlib import Path

import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.tools.similarity.service import SimilarityService
from mightymodels_plugin.tools.similarity.spool import SPOOL_DIRECTORY


@pytest.fixture
def spool(data_directory: Path) -> Path:
    return data_directory.joinpath(SPOOL_DIRECTORY)


@pytest.fixture
def similarity_service(repository_database: Database, spool: Path) -> SimilarityService:
    return SimilarityService(database=repository_database, spool=spool)
