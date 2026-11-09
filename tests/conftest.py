import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.analyses import run_analyses
from engine.checks import check_all
from engine.extract import extract_all
from engine.read import read_folder
from engine.summarize import template
from scripts.make_license_data import make as make_lic
from scripts.make_sample_data import make


def build(folder):
    ledger = extract_all(read_folder(folder))
    check_all(ledger)
    return ledger


@pytest.fixture(scope="session")
def sample_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("sample")
    make(d, seeded=True)
    return d


@pytest.fixture(scope="session")
def clean_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("clean")
    make(d, seeded=False)
    return d


@pytest.fixture()
def sample(sample_dir):
    return build(sample_dir)


@pytest.fixture()
def clean(clean_dir):
    return build(clean_dir)


def results_by_id(ledger):
    return {r.id: r for r in run_analyses(ledger)}


def summary(ledger):
    res = list(results_by_id(ledger).values())
    return res, template(res)


@pytest.fixture(scope="module")
def lic_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("lic")
    make_lic(d)
    return d
