# Mock astrbot modules before importing the plugin
import sys
from unittest.mock import MagicMock

# Create mock modules
mock_astrbot = MagicMock()
mock_astrbot.api = MagicMock()
mock_astrbot.api.event = MagicMock()
mock_astrbot.api.star = MagicMock()
mock_astrbot.api.logger = MagicMock()

# Mock decorators to pass through
def mock_register(*args, **kwargs):
    def decorator(cls):
        cls._register_args = args
        cls._register_kwargs = kwargs
        return cls
    return decorator

mock_astrbot.api.star.register = mock_register

# Mock filter
def mock_command(name, alias=None):
    def decorator(func):
        func._command_name = name
        func._command_alias = alias or set()
        return func
    return decorator

def mock_llm_tool(name):
    def decorator(func):
        func._llm_tool_name = name
        return func
    return decorator

mock_astrbot.api.event.filter = MagicMock()
mock_astrbot.api.event.filter.command = mock_command
mock_astrbot.api.event.filter.llm_tool = mock_llm_tool

# Mock classes
class MockStar:
    def __init__(self, context):
        self.context = context

class MockContext:
    pass

class MockAstrMessageEvent:
    def __init__(self, message_str=""):
        self.message_str = message_str
        self._results = []
    
    def plain_result(self, text):
        self._results.append(text)
        return text

mock_astrbot.api.star.Star = MockStar
mock_astrbot.api.star.Context = MockContext
mock_astrbot.api.event.AstrMessageEvent = MockAstrMessageEvent

sys.modules['astrbot'] = mock_astrbot
sys.modules['astrbot.api'] = mock_astrbot.api
sys.modules['astrbot.api.event'] = mock_astrbot.api.event
sys.modules['astrbot.api.star'] = mock_astrbot.api.star

# Mock aiohttp to avoid dependency
mock_aiohttp = MagicMock()
mock_aiohttp.ClientTimeout = MagicMock()
mock_aiohttp.ClientSession = MagicMock()
mock_aiohttp.ClientError = Exception
sys.modules['aiohttp'] = mock_aiohttp

import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import json

from main import WeatherPlugin, CAIYUN_SKYCON_MAP


class TestWeatherPluginInit(unittest.TestCase):
    """Test plugin initialization"""

    def test_default_config(self):
        """Test plugin with default config"""
        plugin = WeatherPlugin(MockContext())
        self.assertEqual(plugin.provider, "wttr")
        self.assertEqual(plugin.caiyun_api_key, "")
        self.assertEqual(plugin.caiyun_api_version, "v2.6")
        self.assertEqual(plugin.wttr_base_url, "https://wttr.in")
    
    def test_caiyun_config(self):
        """Test plugin with caiyun config"""
        config = {
            "weather_provider": "caiyun",
            "caiyun_api_key": "test_key",
            "caiyun_api_version": "v2.5"
        }
        plugin = WeatherPlugin(MockContext(), config)
        self.assertEqual(plugin.provider, "caiyun")
        self.assertEqual(plugin.caiyun_api_key, "test_key")
        self.assertEqual(plugin.caiyun_api_version, "v2.5")
    
    def test_wttr_config(self):
        """Test plugin with wttr config"""
        config = {
            "weather_provider": "wttr"
        }
        plugin = WeatherPlugin(MockContext(), config)
        self.assertEqual(plugin.provider, "wttr")


class TestParseDays(unittest.TestCase):
    """Test _parse_days method"""

    def setUp(self):
        self.plugin = WeatherPlugin(MockContext())

    def test_tomorrow_variants(self):
        """Test tomorrow parsing"""
        self.assertEqual(self.plugin._parse_days("明天"), 1)
        self.assertEqual(self.plugin._parse_days("明日"), 1)
        self.assertEqual(self.plugin._parse_days("tomorrow"), 1)
        self.assertEqual(self.plugin._parse_days(" 明天 "), 1)

    def test_day_after_tomorrow(self):
        """Test day after tomorrow parsing"""
        self.assertEqual(self.plugin._parse_days("后天"), 2)
        self.assertEqual(self.plugin._parse_days("後天"), 2)
        self.assertEqual(self.plugin._parse_days("day after tomorrow"), 2)

    def test_three_days_later(self):
        """Test three days later parsing"""
        self.assertEqual(self.plugin._parse_days("大后天"), 3)
        self.assertEqual(self.plugin._parse_days("大後天"), 3)
        self.assertEqual(self.plugin._parse_days("三天后"), 3)
        self.assertEqual(self.plugin._parse_days("3天后"), 3)

    def test_numeric_days(self):
        """Test numeric day parsing"""
        self.assertEqual(self.plugin._parse_days("0"), 0)
        self.assertEqual(self.plugin._parse_days("1"), 1)
        self.assertEqual(self.plugin._parse_days("3"), 3)
        self.assertEqual(self.plugin._parse_days("7"), 7)

    def test_negative_days(self):
        """Test negative day handling"""
        self.assertEqual(self.plugin._parse_days("-1"), 0)

    def test_max_days(self):
        """Test max day limit"""
        self.assertEqual(self.plugin._parse_days("10"), 7)
        self.assertEqual(self.plugin._parse_days("100"), 7)

    def test_invalid_input(self):
        """Test invalid input handling"""
        self.assertEqual(self.plugin._parse_days("abc"), 0)
        self.assertEqual(self.plugin._parse_days(""), 0)
        self.assertEqual(self.plugin._parse_days("你好"), 0)


class TestDegreeToDirection(unittest.TestCase):
    """Test _degree_to_direction method"""

    def setUp(self):
        self.plugin = WeatherPlugin(MockContext())

    def test_cardinal_directions(self):
        """Test cardinal directions"""
        self.assertEqual(self.plugin._degree_to_direction(0), "北")
        self.assertEqual(self.plugin._degree_to_direction(90), "东")
        self.assertEqual(self.plugin._degree_to_direction(180), "南")
        self.assertEqual(self.plugin._degree_to_direction(270), "西")
        self.assertEqual(self.plugin._degree_to_direction(360), "北")

    def test_intercardinal_directions(self):
        """Test intercardinal directions"""
        self.assertEqual(self.plugin._degree_to_direction(45), "东北")
        self.assertEqual(self.plugin._degree_to_direction(135), "东南")
        self.assertEqual(self.plugin._degree_to_direction(225), "西南")
        self.assertEqual(self.plugin._degree_to_direction(315), "西北")

    def test_all_directions(self):
        """Test all 16 directions"""
        directions = ["北", "北东北", "东北", "东东北", "东", "东东南", "东南", "南东南",
                      "南", "南西南", "西南", "西西南", "西", "西西北", "西北", "北西北"]
        for i, expected in enumerate(directions):
            degree = i * 22.5
            result = self.plugin._degree_to_direction(degree)
            self.assertEqual(result, expected, f"Failed at degree {degree}")

    def test_wraparound(self):
        """Test degree wraparound"""
        self.assertEqual(self.plugin._degree_to_direction(720), "北")
        self.assertEqual(self.plugin._degree_to_direction(-90), "西")


class TestFormatCaiyunWeather(unittest.TestCase):
    """Test _format_caiyun_weather method"""

    def setUp(self):
        self.plugin = WeatherPlugin(MockContext())

    def test_basic_formatting(self):
        """Test basic weather formatting"""
        data = {
            "city": "北京",
            "realtime": {
                "temperature": 25,
                "apparent_temperature": 28,
                "humidity": 0.6,
                "skycon": "CLEAR_DAY",
                "visibility": 10,
                "pressure": 101325,
                "wind": {
                    "speed": 3.5,
                    "direction": 180
                }
            }
        }
        result = self.plugin._format_caiyun_weather(data)
        self.assertIn("北京", result)
        self.assertIn("25°C", result)
        self.assertIn("28°C", result)
        self.assertIn("60%", result)
        self.assertIn("晴", result)
        self.assertIn("3.5 m/s", result)
        self.assertIn("南", result)
        self.assertIn("1013.2 hPa", result)

    def test_with_air_quality(self):
        """Test formatting with air quality"""
        data = {
            "city": "上海",
            "realtime": {
                "temperature": 20,
                "apparent_temperature": 22,
                "humidity": 0.7,
                "skycon": "CLOUDY",
                "visibility": 8,
                "pressure": 100000,
                "wind": {"speed": 2, "direction": 90},
                "air_quality": {
                    "pm25": 35,
                    "aqi": {"chn": 80}
                }
            }
        }
        result = self.plugin._format_caiyun_weather(data)
        self.assertIn("空气质量", result)
        self.assertIn("AQI 80", result)
        self.assertIn("PM2.5 35", result)

    def test_with_life_index(self):
        """Test formatting with life index"""
        data = {
            "city": "广州",
            "realtime": {
                "temperature": 30,
                "apparent_temperature": 35,
                "humidity": 0.8,
                "skycon": "LIGHT_RAIN",
                "visibility": 5,
                "pressure": 101000,
                "wind": {"speed": 1, "direction": 0},
                "life_index": {
                    "ultraviolet": {"desc": "强"},
                    "comfort": {"desc": "闷热"}
                }
            }
        }
        result = self.plugin._format_caiyun_weather(data)
        self.assertIn("生活指数", result)
        self.assertIn("紫外线 强", result)
        self.assertIn("舒适度 闷热", result)

    def test_unknown_skycon(self):
        """Test unknown skycon handling"""
        data = {
            "city": "Test",
            "realtime": {
                "temperature": 20,
                "apparent_temperature": 20,
                "humidity": 0.5,
                "skycon": "UNKNOWN_CODE",
                "visibility": 10,
                "pressure": 101325,
                "wind": {"speed": 0, "direction": 0}
            }
        }
        result = self.plugin._format_caiyun_weather(data)
        self.assertIn("UNKNOWN_CODE", result)

    def test_integer_humidity(self):
        """Test integer humidity handling"""
        data = {
            "city": "Test",
            "realtime": {
                "temperature": 20,
                "apparent_temperature": 20,
                "humidity": 50,
                "skycon": "CLEAR_DAY",
                "visibility": 10,
                "pressure": 101325,
                "wind": {"speed": 0, "direction": 0}
            }
        }
        result = self.plugin._format_caiyun_weather(data)
        self.assertIn("5000%", result)


class TestFormatCaiyunForecast(unittest.TestCase):
    """Test _format_caiyun_forecast method"""

    def setUp(self):
        self.plugin = WeatherPlugin(MockContext())

    def test_basic_forecast(self):
        """Test basic forecast formatting"""
        data = {
            "city": "北京",
            "days": 3,
            "daily": {
                "temperature": [
                    {"date": "2024-01-01", "max": 10, "min": 0, "avg": 5},
                    {"date": "2024-01-02", "max": 12, "min": 2, "avg": 7},
                    {"date": "2024-01-03", "max": 8, "min": -2, "avg": 3}
                ],
                "skycon": [
                    {"value": "CLEAR_DAY"},
                    {"value": "CLOUDY"},
                    {"value": "LIGHT_RAIN"}
                ],
                "precipitation": [
                    {"probability": 0},
                    {"probability": 0.2},
                    {"probability": 0.8}
                ],
                "wind": [
                    {"avg": {"speed": 3, "direction": 0}},
                    {"avg": {"speed": 5, "direction": 90}},
                    {"avg": {"speed": 2, "direction": 180}}
                ],
                "humidity": [
                    {"avg": 0.4},
                    {"avg": 0.5},
                    {"avg": 0.8}
                ],
                "astro": [
                    {"sunrise": {"time": "07:00"}, "sunset": {"time": "17:00"}},
                    {"sunrise": {"time": "07:01"}, "sunset": {"time": "17:01"}},
                    {"sunrise": {"time": "07:02"}, "sunset": {"time": "17:02"}}
                ]
            }
        }
        result = self.plugin._format_caiyun_forecast(data)
        self.assertIn("北京 天气预报", result)
        self.assertIn("今天", result)
        self.assertIn("明天", result)
        self.assertIn("后天", result)
        self.assertIn("10°C", result)
        self.assertIn("晴", result)
        self.assertIn("阴", result)
        self.assertIn("小雨", result)
        self.assertIn("日出", result)
        self.assertIn("日落", result)

    def test_partial_data(self):
        """Test forecast with missing optional data"""
        data = {
            "city": "Test",
            "days": 1,
            "daily": {
                "temperature": [
                    {"date": "2024-01-01", "max": 20, "min": 10, "avg": 15}
                ],
                "skycon": [{"value": "CLEAR_DAY"}],
                "precipitation": [],
                "wind": [],
                "humidity": [],
                "astro": []
            }
        }
        result = self.plugin._format_caiyun_forecast(data)
        self.assertIn("Test 天气预报", result)
        self.assertIn("20°C", result)


class TestParseWttrWeather(unittest.TestCase):
    """Test _parse_wttr_weather method"""

    def setUp(self):
        self.plugin = WeatherPlugin(MockContext())

    def test_basic_parsing(self):
        """Test basic weather data parsing"""
        data = {
            "current_condition": [{
                "weatherDesc": [{"value": "Sunny"}],
                "temp_C": "25",
                "FeelsLikeC": "28",
                "humidity": "60",
                "windspeedKmph": "10",
                "winddir16Point": "SW",
                "visibility": "10",
                "pressure": "1015",
                "observation_time": "12:00 PM"
            }],
            "nearest_area": [{
                "areaName": [{"value": "Beijing"}],
                "country": [{"value": "China"}]
            }]
        }
        result = self.plugin._parse_wttr_weather(data, "Beijing")
        self.assertIsNotNone(result)
        self.assertEqual(result["city"], "Beijing, China")  # type: ignore[index]
        self.assertEqual(result["description"], "Sunny")  # type: ignore[index]
        self.assertEqual(result["temp_c"], "25")  # type: ignore[index]
        self.assertEqual(result["wind_speed"], "10")  # type: ignore[index]

    def test_no_nearest_area(self):
        """Test parsing without nearest_area"""
        data = {
            "current_condition": [{
                "weatherDesc": [{"value": "Cloudy"}],
                "temp_C": "20",
                "FeelsLikeC": "20",
                "humidity": "70",
                "windspeedKm/h": "5",
                "winddir16Point": "N",
                "visibility": "8",
                "pressure": "1010",
                "observation_time": "10:00 AM"
            }]
        }
        result = self.plugin._parse_wttr_weather(data, "Shanghai")
        self.assertIsNotNone(result)
        self.assertEqual(result["city"], "Shanghai")  # type: ignore[index]

    def test_empty_current_condition(self):
        """Test parsing with empty current_condition"""
        data = {
            "current_condition": [],
            "nearest_area": [{}]
        }
        result = self.plugin._parse_wttr_weather(data, "Test")
        self.assertIsNone(result)

    def test_missing_fields(self):
        """Test parsing with missing fields"""
        data = {
            "current_condition": [{}],
            "nearest_area": [{}]
        }
        result = self.plugin._parse_wttr_weather(data, "Test")
        self.assertIsNotNone(result)
        self.assertEqual(result["description"], "未知")  # type: ignore[index]


class TestParseWttrForecast(unittest.TestCase):
    """Test _parse_wttr_forecast method"""

    def setUp(self):
        self.plugin = WeatherPlugin(MockContext())

    def test_basic_forecast_parsing(self):
        """Test basic forecast parsing"""
        data = {
            "nearest_area": [{
                "areaName": [{"value": "Beijing"}],
                "country": [{"value": "China"}]
            }],
            "weather": [
                {
                    "date": "2024-01-01",
                    "maxtempC": "10",
                    "mintempC": "0",
                    "avgtempC": "5",
                    "uvIndex": "3",
                    "hourly": [
                        {"time": "0", "weatherDesc": [{"value": "Clear"}], "chanceofrain": "0", "windspeedKmph": "5", "winddir16Point": "N", "humidity": "40"},
                        {"time": "1200", "weatherDesc": [{"value": "Sunny"}], "chanceofrain": "0", "windspeedKmph": "10", "winddir16Point": "S", "humidity": "35"}
                    ],
                    "astronomy": [{"sunrise": "07:00", "sunset": "17:00"}]
                },
                {
                    "date": "2024-01-02",
                    "maxtempC": "12",
                    "mintempC": "2",
                    "avgtempC": "7",
                    "uvIndex": "4",
                    "hourly": [
                        {"time": "0", "weatherDesc": [{"value": "Cloudy"}], "chanceofrain": "20", "windspeedKmph": "8", "winddir16Point": "SW", "humidity": "50"}
                    ],
                    "astronomy": [{"sunrise": "07:01", "sunset": "17:01"}]
                }
            ]
        }
        result = self.plugin._parse_wttr_forecast(data, "Beijing", 2)
        self.assertIsNotNone(result)
        self.assertEqual(result["city"], "Beijing, China")  # type: ignore[index]
        self.assertEqual(len(result["forecast"]), 2)  # type: ignore[index]
        
        day1 = result["forecast"][0]  # type: ignore[index]
        self.assertEqual(day1["description"], "Sunny")
        self.assertEqual(day1["wind_speed"], "10")
        
        day2 = result["forecast"][1]  # type: ignore[index]
        self.assertEqual(day2["description"], "Cloudy")

    def test_no_weather_data(self):
        """Test parsing with no weather data"""
        data = {
            "nearest_area": [{}],
            "weather": []
        }
        result = self.plugin._parse_wttr_forecast(data, "Test", 3)
        self.assertIsNone(result)

    def test_no_hourly_data(self):
        """Test parsing with no hourly data"""
        data = {
            "nearest_area": [{}],
            "weather": [
                {
                    "date": "2024-01-01",
                    "maxtempC": "20",
                    "mintempC": "10",
                    "avgtempC": "15",
                    "hourly": [],
                    "astronomy": [{}]
                }
            ]
        }
        result = self.plugin._parse_wttr_forecast(data, "Test", 1)
        self.assertIsNotNone(result)
        self.assertEqual(result["forecast"][0]["description"], "")  # type: ignore[index]


class TestFormatWttrWeather(unittest.TestCase):
    """Test _format_wttr_weather method"""

    def setUp(self):
        self.plugin = WeatherPlugin(MockContext())

    def test_basic_formatting(self):
        """Test basic wttr weather formatting"""
        data = {
            "city": "Beijing, China",
            "description": "Sunny",
            "temp_c": "25",
            "feels_like_c": "28",
            "humidity": "60",
            "wind_speed": "10",
            "wind_dir": "SW",
            "visibility": "10",
            "pressure": "1015",
            "observation_time": "12:00 PM"
        }
        result = self.plugin._format_wttr_weather(data)
        self.assertIn("Beijing, China", result)
        self.assertIn("Sunny", result)
        self.assertIn("25°C", result)
        self.assertIn("10 km/h SW", result)
        self.assertIn("12:00 PM", result)

    def test_no_wind_dir(self):
        """Test formatting without wind direction"""
        data = {
            "city": "Test",
            "description": "Cloudy",
            "temp_c": "20",
            "feels_like_c": "20",
            "humidity": "70",
            "wind_speed": "5",
            "wind_dir": "",
            "visibility": "8",
            "pressure": "1010",
            "observation_time": "10:00 AM"
        }
        result = self.plugin._format_wttr_weather(data)
        self.assertIn("5 km/h", result)
        self.assertNotIn("5 km/h ", result)  # No trailing space


class TestFormatWttrForecast(unittest.TestCase):
    """Test _format_wttr_forecast method"""

    def setUp(self):
        self.plugin = WeatherPlugin(MockContext())

    def test_basic_forecast_formatting(self):
        """Test basic forecast formatting"""
        data = {
            "city": "Beijing, China",
            "forecast": [
                {
                    "date": "2024-01-01",
                    "maxtemp_c": "10",
                    "mintemp_c": "0",
                    "avgtemp_c": "5",
                    "description": "Sunny",
                    "chance_of_rain": "0",
                    "wind_speed": "10",
                    "wind_dir": "N",
                    "humidity": "40",
                    "sunrise": "07:00",
                    "sunset": "17:00"
                }
            ]
        }
        result = self.plugin._format_wttr_forecast(data)
        self.assertIn("Beijing, China 天气预报", result)
        self.assertIn("今天", result)
        self.assertIn("Sunny", result)
        self.assertIn("10 km/h N", result)
        self.assertIn("日出: 07:00", result)

    def test_rain_forecast(self):
        """Test forecast with rain probability"""
        data = {
            "city": "Shanghai",
            "forecast": [
                {
                    "date": "2024-01-01",
                    "maxtemp_c": "15",
                    "mintemp_c": "10",
                    "avgtemp_c": "12",
                    "description": "Rainy",
                    "chance_of_rain": "80",
                    "wind_speed": "15",
                    "wind_dir": "SE",
                    "humidity": "80",
                    "sunrise": "",
                    "sunset": ""
                }
            ]
        }
        result = self.plugin._format_wttr_forecast(data)
        self.assertIn("降雨概率: 80%", result)

    def test_multiple_days(self):
        """Test multiple days formatting"""
        data = {
            "city": "Test",
            "forecast": [
                {
                    "date": "2024-01-01",
                    "maxtemp_c": "20",
                    "mintemp_c": "10",
                    "avgtemp_c": "15",
                    "description": "Day1",
                    "chance_of_rain": "0",
                    "wind_speed": "--",
                    "wind_dir": "",
                    "humidity": "--",
                    "sunrise": "",
                    "sunset": ""
                },
                {
                    "date": "2024-01-02",
                    "maxtemp_c": "22",
                    "mintemp_c": "12",
                    "avgtemp_c": "17",
                    "description": "Day2",
                    "chance_of_rain": "0",
                    "wind_speed": "--",
                    "wind_dir": "",
                    "humidity": "--",
                    "sunrise": "",
                    "sunset": ""
                },
                {
                    "date": "2024-01-03",
                    "maxtemp_c": "18",
                    "mintemp_c": "8",
                    "avgtemp_c": "13",
                    "description": "Day3",
                    "chance_of_rain": "0",
                    "wind_speed": "--",
                    "wind_dir": "",
                    "humidity": "--",
                    "sunrise": "",
                    "sunset": ""
                },
                {
                    "date": "2024-01-04",
                    "maxtemp_c": "16",
                    "mintemp_c": "6",
                    "avgtemp_c": "11",
                    "description": "Day4",
                    "chance_of_rain": "0",
                    "wind_speed": "--",
                    "wind_dir": "",
                    "humidity": "--",
                    "sunrise": "",
                    "sunset": ""
                }
            ]
        }
        result = self.plugin._format_wttr_forecast(data)
        self.assertIn("今天", result)
        self.assertIn("明天", result)
        self.assertIn("后天", result)
        self.assertIn("第4天", result)


class TestCaiyunSkyconMap(unittest.TestCase):
    """Test CAIYUN_SKYCON_MAP completeness"""

    def test_all_skycons_mapped(self):
        """Test that common skycon values are mapped"""
        expected_keys = [
            "CLEAR_DAY", "CLEAR_NIGHT", "PARTLY_CLOUDY_DAY", "PARTLY_CLOUDY_NIGHT",
            "CLOUDY", "LIGHT_HAZE", "MODERATE_HAZE", "HEAVY_HAZE",
            "LIGHT_RAIN", "MODERATE_RAIN", "HEAVY_RAIN", "STORM_RAIN",
            "FOG", "LIGHT_SNOW", "MODERATE_SNOW", "HEAVY_SNOW", "STORM_SNOW",
            "DUST", "SAND", "WIND"
        ]
        for key in expected_keys:
            self.assertIn(key, CAIYUN_SKYCON_MAP)

    def test_chinese_descriptions(self):
        """Test that descriptions are in Chinese"""
        for value in CAIYUN_SKYCON_MAP.values():
            self.assertIsInstance(value, str)
            self.assertTrue(len(value) > 0)


class TestAsyncMethods(unittest.IsolatedAsyncioTestCase):
    """Test async methods with mocked aiohttp"""

    def setUp(self):
        self.plugin = WeatherPlugin(MockContext())

    @patch('aiohttp.ClientSession')
    async def test_geocode_city_success(self, mock_session_class):
        """Test successful geocoding"""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[{
            "lon": "116.4074",
            "lat": "39.9042"
        }])
        
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_session_class.return_value = mock_session
        
        result = await self.plugin._geocode_city("Beijing")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result[0], 116.4074, places=3)  # type: ignore[index]
        self.assertAlmostEqual(result[1], 39.9042, places=3)  # type: ignore[index]

    @patch('aiohttp.ClientSession')
    async def test_geocode_city_failure(self, mock_session_class):
        """Test failed geocoding"""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 404
        
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_session_class.return_value = mock_session
        
        result = await self.plugin._geocode_city("UnknownCity")
        self.assertIsNone(result)

    @patch('aiohttp.ClientSession')
    async def test_fetch_wttr_raw_success(self, mock_session_class):
        """Test successful wttr fetch"""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=json.dumps({
            "current_condition": [{"temp_C": "25"}]
        }))
        
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_session_class.return_value = mock_session
        
        result = await self.plugin._fetch_wttr_raw("Beijing")
        self.assertIsNotNone(result)
        self.assertEqual(result["current_condition"][0]["temp_C"], "25")  # type: ignore[index]

    @patch('aiohttp.ClientSession')
    async def test_fetch_wttr_raw_http_error(self, mock_session_class):
        """Test wttr fetch with HTTP error"""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 404
        
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_session_class.return_value = mock_session
        
        result = await self.plugin._fetch_wttr_raw("UnknownCity")
        self.assertIsNone(result)

    @patch('aiohttp.ClientSession')
    async def test_fetch_wttr_raw_json_error(self, mock_session_class):
        """Test wttr fetch with invalid JSON"""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="invalid json")
        
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_session_class.return_value = mock_session
        
        result = await self.plugin._fetch_wttr_raw("Beijing")
        self.assertIsNone(result)

    @patch('aiohttp.ClientSession')
    async def test_fetch_caiyun_api_success(self, mock_session_class):
        """Test successful caiyun API call"""
        self.plugin.caiyun_api_key = "test_key"
        
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "status": "ok",
            "result": {"realtime": {"temperature": 25}}
        })
        
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_session_class.return_value = mock_session
        
        # Mock geocode to return coordinates
        with patch.object(self.plugin, '_geocode_city', new=AsyncMock(return_value=(116.4, 39.9))):
            result = await self.plugin._fetch_caiyun_api("Beijing")
            self.assertIsNotNone(result)
            self.assertEqual(result["status"], "ok")  # type: ignore[index]

    @patch('aiohttp.ClientSession')
    async def test_fetch_caiyun_api_error_status(self, mock_session_class):
        """Test caiyun API with error status"""
        self.plugin.caiyun_api_key = "test_key"
        
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "status": "error",
            "error": "invalid key"
        })
        
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_session_class.return_value = mock_session
        
        with patch.object(self.plugin, '_geocode_city', new=AsyncMock(return_value=(116.4, 39.9))):
            result = await self.plugin._fetch_caiyun_api("Beijing")
            self.assertIsNone(result)


class TestCommands(unittest.IsolatedAsyncioTestCase):
    """Test command handlers"""

    def setUp(self):
        self.plugin = WeatherPlugin(MockContext())

    async def test_query_weather_no_args(self):
        """Test weather command with no arguments"""
        event = MockAstrMessageEvent("/weather")
        
        results = []
        async for result in self.plugin.query_weather(event):
            results.append(result)
        
        self.assertEqual(len(results), 1)
        self.assertIn("请输入城市名称", results[0])

    async def test_query_forecast_no_args(self):
        """Test forecast command with no arguments"""
        event = MockAstrMessageEvent("/forecast")
        
        results = []
        async for result in self.plugin.query_forecast(event):
            results.append(result)
        
        self.assertEqual(len(results), 1)
        self.assertIn("请输入城市名称", results[0])

    async def test_setweather_no_args(self):
        """Test setweather command with no arguments"""
        event = MockAstrMessageEvent("/setweather")
        
        results = []
        async for result in self.plugin.set_weather_provider(event):
            results.append(result)
        
        self.assertEqual(len(results), 1)
        self.assertIn("wttr.in", results[0])

    async def test_setweather_wttr(self):
        """Test setting weather provider to wttr"""
        event = MockAstrMessageEvent("/setweather wttr")
        
        results = []
        async for result in self.plugin.set_weather_provider(event):
            results.append(result)
        
        self.assertEqual(len(results), 1)
        self.assertIn("wttr.in", results[0])
        self.assertEqual(self.plugin.provider, "wttr")

    async def test_setweather_caiyun_no_key(self):
        """Test setting weather provider to caiyun without key"""
        event = MockAstrMessageEvent("/setweather caiyun")
        
        results = []
        async for result in self.plugin.set_weather_provider(event):
            results.append(result)
        
        self.assertEqual(len(results), 1)
        self.assertIn("API Key", results[0])

    async def test_setweather_invalid_provider(self):
        """Test setting invalid weather provider"""
        event = MockAstrMessageEvent("/setweather invalid")
        
        results = []
        async for result in self.plugin.set_weather_provider(event):
            results.append(result)
        
        self.assertEqual(len(results), 1)
        self.assertIn("无效", results[0])

    @patch.object(WeatherPlugin, '_do_fetch_weather', new_callable=AsyncMock)
    async def test_query_weather_with_city(self, mock_fetch):
        """Test weather command with city"""
        mock_fetch.return_value = "北京: 25°C Sunny"
        event = MockAstrMessageEvent("/weather Beijing")
        
        results = []
        async for result in self.plugin.query_weather(event):
            results.append(result)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], "北京: 25°C Sunny")
        mock_fetch.assert_called_once_with("Beijing")

    @patch.object(WeatherPlugin, '_do_fetch_forecast', new_callable=AsyncMock)
    async def test_query_forecast_with_city(self, mock_fetch):
        """Test forecast command with city"""
        mock_fetch.return_value = "Forecast for Beijing"
        event = MockAstrMessageEvent("/forecast Beijing 3")
        
        results = []
        async for result in self.plugin.query_forecast(event):
            results.append(result)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], "Forecast for Beijing")
        mock_fetch.assert_called_once_with("Beijing", 3)

    @patch.object(WeatherPlugin, '_do_fetch_forecast', new_callable=AsyncMock)
    async def test_query_weather_with_days(self, mock_fetch):
        """Test weather command with city and days"""
        mock_fetch.return_value = "3-day forecast"
        event = MockAstrMessageEvent("/weather Beijing 3")
        
        results = []
        async for result in self.plugin.query_weather(event):
            results.append(result)
        
        self.assertEqual(len(results), 1)
        mock_fetch.assert_called_once_with("Beijing", 3)


class TestLLMTool(unittest.IsolatedAsyncioTestCase):
    """Test LLM tool methods"""

    def setUp(self):
        self.plugin = WeatherPlugin(MockContext())

    @patch.object(WeatherPlugin, '_do_fetch_weather', new_callable=AsyncMock)
    async def test_get_weather_tool_current(self, mock_fetch):
        """Test get_weather_tool for current weather"""
        mock_fetch.return_value = "Current weather"
        event = MockAstrMessageEvent()
        
        result = await self.plugin.get_weather_tool(event, "Beijing", 0)
        self.assertEqual(result, "Current weather")
        mock_fetch.assert_called_once_with("Beijing")

    @patch.object(WeatherPlugin, '_do_fetch_forecast', new_callable=AsyncMock)
    async def test_get_weather_tool_forecast(self, mock_fetch):
        """Test get_weather_tool for forecast"""
        mock_fetch.return_value = "Forecast"
        event = MockAstrMessageEvent()
        
        result = await self.plugin.get_weather_tool(event, "Beijing", 3)
        self.assertEqual(result, "Forecast")
        mock_fetch.assert_called_once_with("Beijing", 3)


class TestDoFetchWeather(unittest.IsolatedAsyncioTestCase):
    """Test _do_fetch_weather method"""

    def setUp(self):
        self.plugin = WeatherPlugin(MockContext())

    @patch.object(WeatherPlugin, '_fetch_wttr_weather', new_callable=AsyncMock)
    @patch.object(WeatherPlugin, '_format_wttr_weather')
    async def test_wttr_success(self, mock_format, mock_fetch):
        """Test successful wttr weather fetch"""
        mock_fetch.return_value = {"temp_c": "25"}
        mock_format.return_value = "Formatted weather"
        
        result = await self.plugin._do_fetch_weather("Beijing")
        self.assertEqual(result, "Formatted weather")
        mock_fetch.assert_called_once_with("Beijing")
        mock_format.assert_called_once_with({"temp_c": "25"})

    @patch.object(WeatherPlugin, '_fetch_wttr_weather', new_callable=AsyncMock)
    async def test_wttr_failure(self, mock_fetch):
        """Test wttr weather fetch failure"""
        mock_fetch.return_value = None
        
        result = await self.plugin._do_fetch_weather("UnknownCity")
        self.assertIn("无法获取", result)
        self.assertIn("UnknownCity", result)

    @patch.object(WeatherPlugin, '_fetch_caiyun_weather', new_callable=AsyncMock)
    @patch.object(WeatherPlugin, '_format_caiyun_weather')
    @patch.object(WeatherPlugin, '_fetch_wttr_weather', new_callable=AsyncMock)
    @patch.object(WeatherPlugin, '_format_wttr_weather')
    async def test_caiyun_fallback(self, mock_wttr_format, mock_wttr_fetch, 
                                     mock_caiyun_format, mock_caiyun_fetch):
        """Test caiyun fallback to wttr"""
        self.plugin.provider = "caiyun"
        self.plugin.caiyun_api_key = "test_key"
        
        mock_caiyun_fetch.return_value = None  # Caiyun fails
        mock_wttr_fetch.return_value = {"temp_c": "20"}
        mock_wttr_format.return_value = "Wttr weather"
        
        result = await self.plugin._do_fetch_weather("Beijing")
        self.assertEqual(result, "Wttr weather")
        mock_caiyun_fetch.assert_called_once_with("Beijing")
        mock_wttr_fetch.assert_called_once_with("Beijing")


class TestDoFetchForecast(unittest.IsolatedAsyncioTestCase):
    """Test _do_fetch_forecast method"""

    def setUp(self):
        self.plugin = WeatherPlugin(MockContext())

    @patch.object(WeatherPlugin, '_fetch_wttr_forecast', new_callable=AsyncMock)
    @patch.object(WeatherPlugin, '_format_wttr_forecast')
    async def test_wttr_forecast_success(self, mock_format, mock_fetch):
        """Test successful wttr forecast fetch"""
        mock_fetch.return_value = {"forecast": []}
        mock_format.return_value = "Formatted forecast"
        
        result = await self.plugin._do_fetch_forecast("Beijing", 3)
        self.assertEqual(result, "Formatted forecast")
        mock_fetch.assert_called_once_with("Beijing", 3)

    @patch.object(WeatherPlugin, '_fetch_wttr_forecast', new_callable=AsyncMock)
    async def test_wttr_forecast_failure(self, mock_fetch):
        """Test wttr forecast fetch failure"""
        mock_fetch.return_value = None
        
        result = await self.plugin._do_fetch_forecast("UnknownCity", 3)
        self.assertIn("无法获取", result)


if __name__ == '__main__':
    unittest.main()
