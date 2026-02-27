from pathlib import Path

import pytest


@pytest.fixture
def testdata_dir() -> Path:
    return Path(__file__).parent.parent / "testdata"


@pytest.fixture
def config_testdata(testdata_dir: Path) -> Path:
    return testdata_dir / "config"
