import json
from datetime import datetime
from unittest import mock

import requests_mock
import pytest

import roof_analysis as ra


def test_compute_score():
    prop = ra.PropertyDetails(address="123", year_built=2010, square_feet=2000)
    prop.roof_age = 4
    prop.permits = [ra.PermitRecord(date=datetime.now(), description="New roof")]
    prop.weather_events = [{"type": "hail"}, {"type": "wind"}]
    score = ra.compute_score(prop)
    # 10 for roof age - 4 for events +1 for permit = 7
    assert score == 7


def test_fetch_noaa_events():
    with requests_mock.Mocker() as m:
        m.get(ra.Config.NOAA_URL, json={"events": [{"type": "hail"}]})
        events = ra.fetch_noaa_events("30519")
    assert events == [{"type": "hail"}]


def test_fetch_gwinnett_permits():
    html = """
    <table class='permits'>
        <tr><td>01/01/2023</td><td>Roof Repair</td></tr>
    </table>
    """
    with requests_mock.Mocker() as m:
        m.get(ra.Config.GWinnett_URL, text=html)
        permits = ra.fetch_gwinnett_permits("30519")
    assert permits[0].description == "Roof Repair"


def test_fetch_zillow_details():
    html = """
    <article data-year-built='2015' data-sqft='1800'>
        <div class='address'>123 Main</div>
    </article>
    """
    with requests_mock.Mocker() as m:
        m.get(ra.Config.ZILLOW_URL + "30519", text=html)
        details = ra.fetch_zillow_details("30519")
    assert details[0].address == "123 Main"


def test_update_google_sheet(monkeypatch):
    sheet = mock.Mock()
    gc = mock.Mock(open_by_key=mock.Mock(return_value=mock.Mock(worksheet=mock.Mock(return_value=sheet))))
    creds = mock.Mock()

    monkeypatch.setattr(ra, "gspread", mock.Mock(authorize=mock.Mock(return_value=gc)))
    monkeypatch.setattr(ra, "Credentials", mock.Mock(from_service_account_file=mock.Mock(return_value=creds)))

    ra.update_google_sheet([["a"]], "Sheet1")
    sheet.clear.assert_called()
    sheet.update.assert_called_with("A1", [["a"]])
