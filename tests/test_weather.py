from __future__ import annotations

import unittest
from unittest.mock import Mock

import requests

from jarvis_ai.weather import FORECAST_URL, GEOCODING_URL, WeatherService


class FakeResponse:
    def __init__(self, payload: dict, *, status_error: Exception | None = None) -> None:
        self.payload = payload
        self.status_error = status_error

    def raise_for_status(self) -> None:
        if self.status_error:
            raise self.status_error

    def json(self) -> dict:
        return self.payload


class WeatherServiceTests(unittest.TestCase):
    def test_returns_a_spoken_current_weather_summary(self) -> None:
        geocoding = FakeResponse(
            {
                "results": [
                    {
                        "name": "Mumbai",
                        "admin1": "Maharashtra",
                        "latitude": 19.07,
                        "longitude": 72.88,
                    }
                ]
            }
        )
        forecast = FakeResponse(
            {
                "current": {
                    "temperature_2m": 30.4,
                    "apparent_temperature": 34.1,
                    "relative_humidity_2m": 72,
                    "precipitation": 0,
                    "weather_code": 2,
                    "wind_speed_10m": 11.6,
                },
                "daily": {"precipitation_probability_max": [40]},
            }
        )
        http_get = Mock(side_effect=[geocoding, forecast])
        service = WeatherService(http_get=http_get)

        result = service.current_summary("Mumbai")

        self.assertIn("Mumbai, Maharashtra", result)
        self.assertIn("partly cloudy", result)
        self.assertIn("30 degrees Celsius", result)
        self.assertIn("rain chance is 40 percent", result)
        self.assertEqual(http_get.call_args_list[0].args[0], GEOCODING_URL)
        self.assertEqual(http_get.call_args_list[1].args[0], FORECAST_URL)
        self.assertEqual(http_get.call_args_list[0].kwargs["params"]["name"], "Mumbai")
        self.assertNotIn("apikey", http_get.call_args_list[1].kwargs["params"])

    def test_goa_uses_verified_panaji_coordinates_without_geocoding(self) -> None:
        forecast = FakeResponse(
            {
                "current": {
                    "temperature_2m": 29,
                    "apparent_temperature": 33,
                    "relative_humidity_2m": 75,
                    "precipitation": 0,
                    "weather_code": 1,
                    "wind_speed_10m": 8,
                },
                "daily": {"precipitation_probability_max": [20]},
            }
        )
        http_get = Mock(return_value=forecast)

        result = WeatherService(http_get=http_get).current_summary("Goa")

        self.assertIn("Panaji, Goa", result)
        http_get.assert_called_once()
        self.assertEqual(http_get.call_args.args[0], FORECAST_URL)
        self.assertEqual(http_get.call_args.kwargs["params"]["latitude"], 15.4909)
        self.assertEqual(http_get.call_args.kwargs["params"]["longitude"], 73.8278)

    def test_reports_an_unknown_city(self) -> None:
        service = WeatherService(http_get=Mock(return_value=FakeResponse({})))

        with self.assertRaisesRegex(Exception, "could not find a place"):
            service.current_summary("Not A Real City")

    def test_reports_network_failure(self) -> None:
        service = WeatherService(http_get=Mock(side_effect=requests.Timeout()))

        with self.assertRaisesRegex(Exception, "could not reach"):
            service.current_summary("Goa")


if __name__ == "__main__":
    unittest.main()
