"""
AstrBot Weather Plugin
A simple weather query plugin using wttr.in API (no API key required)
Supports both command-based and natural language queries
Supports current weather and future forecast queries
"""

from typing import Optional, List
import aiohttp
import json
import traceback
from datetime import datetime, timedelta

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger



@register(
    "astrbot_plugin_weather_counhopig",
    "counhopig",
    "AstrBot 天气查询插件，支持查询全球城市当前及未来天气",
    "1.2.0"
)
class WeatherPlugin(Star):
    """Weather plugin for AstrBot"""
    
    def __init__(self, context: Context):
        super().__init__(context)
        self.base_url = "https://wttr.in"
    
    async def initialize(self):
        """Initialize hook - called when plugin loads"""
        logger.info("天气插件已加载")
    
    @filter.command("weather", alias={"天气", "查天气", "tq"})
    async def query_weather(self, event: AstrMessageEvent):
        """
        Query weather for a city
        Usage: /weather <city> [days|明天|后天] or /天气 <城市名> [天数]
        Example: /weather Beijing, /天气 北京, /天气 北京 3, /天气 北京 明天
        """
        message_str = event.message_str.strip()
        parts = message_str.split(maxsplit=2)
        
        # Parse city name from message
        if len(parts) < 2:
            yield event.plain_result(
                "请输入城市名称\n"
                "使用方法: /weather <城市名> [天数/明天/后天]\n"
                "示例: /weather Beijing 或 /天气 北京 3 或 /天气 北京 明天"
            )
            return
        
        city = parts[1].strip()
        days = 0
        
        # Parse optional days parameter
        if len(parts) >= 3:
            days = self._parse_days(parts[2].strip())
        
        if days > 0:
            # Fetch forecast
            forecast_data = await self._fetch_forecast(city, days)
            if forecast_data is None:
                yield event.plain_result(
                    f"抱歉，无法获取 {city} 的未来天气信息。\n"
                    "可能原因：城市名称错误或天气服务暂时不可用。"
                )
                return
            result = self._format_forecast(forecast_data)
            yield event.plain_result(result)
        else:
            # Fetch current weather
            weather_data = await self._fetch_weather(city)
            if weather_data is None:
                yield event.plain_result(
                    f"抱歉，无法获取 {city} 的天气信息。\n"
                    "可能原因：城市名称错误或天气服务暂时不可用。"
                )
                return
            result = self._format_weather(weather_data)
            yield event.plain_result(result)
    
    @filter.command("forecast", alias={"天气预报", "未来天气", "yltq"})
    async def query_forecast(self, event: AstrMessageEvent):
        """
        Query future weather forecast for a city
        Usage: /forecast <city> [days] or /天气预报 <城市名> [天数]
        Example: /forecast Beijing 3 or /天气预报 上海 3
        """
        message_str = event.message_str.strip()
        parts = message_str.split(maxsplit=2)
        
        if len(parts) < 2:
            yield event.plain_result(
                "请输入城市名称\n"
                "使用方法: /forecast <城市名> [天数] 或 /天气预报 <城市名> [天数]\n"
                "示例: /forecast Beijing 3 或 /天气预报 上海 3"
            )
            return
        
        city = parts[1].strip()
        days = 3  # Default to 3 days
        
        if len(parts) >= 3:
            parsed = self._parse_days(parts[2].strip())
            if parsed > 0:
                days = parsed
        
        forecast_data = await self._fetch_forecast(city, days)
        if forecast_data is None:
            yield event.plain_result(
                f"抱歉，无法获取 {city} 的天气预报。\n"
                "可能原因：城市名称错误或天气服务暂时不可用。"
            )
            return
        
        result = self._format_forecast(forecast_data)
        yield event.plain_result(result)
    
    @filter.llm_tool(name="get_weather")
    async def get_weather_tool(self, event: AstrMessageEvent, location: str, days: int = 0):
        '''获取指定城市的当前天气或未来天气预报信息。

        Args:
            location(string): 城市名称，例如"北京"、"上海"、"香港"
            days(int): 查询未来几天的天气，0表示当前天气，1表示明天，2表示后天，3表示大后天。默认为0。
        '''
        if days and days > 0:
            forecast_data = await self._fetch_forecast(location, days)
            if forecast_data:
                return self._format_forecast(forecast_data)
            return f"抱歉，无法获取 {location} 的未来天气信息。请检查城市名称是否正确。"
        else:
            weather_data = await self._fetch_weather(location)
            if weather_data:
                return self._format_weather(weather_data)
            return f"抱歉，无法获取 {location} 的天气信息。请检查城市名称是否正确。"
    
    def _parse_days(self, text: str) -> int:
        """Parse days parameter from text input"""
        text = text.strip().lower()
        
        # Chinese relative days
        if text in ("明天", "明日", "tomorrow"):
            return 1
        if text in ("后天", "後天", "day after tomorrow"):
            return 2
        if text in ("大后天", "大後天", "三天后", "3天后"):
            return 3
        
        # Numeric parsing
        try:
            days = int(text)
            if days < 0:
                return 0
            if days > 3:
                return 3  # wttr.in free tier supports up to 3 days
            return days
        except ValueError:
            return 0
    
    async def _fetch_raw_data(self, city: str) -> Optional[dict]:
        """Fetch raw weather data from wttr.in API"""
        url = f"{self.base_url}/{city}"
        params = {"format": "j1"}
        text = None
        
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            headers = {
                "User-Agent": "curl/7.68.0",
                "Accept": "application/json"
            }
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        logger.warning(f"Weather API returned status {resp.status} for city: {city}")
                        return None
                    
                    text = await resp.text()
                    data = json.loads(text)
                    return data
                    
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching weather for {city}: {e}")
            return None
        except TimeoutError:
            logger.error(f"Timeout fetching weather for {city}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {city}: {e}")
            logger.debug(f"Response text: {text[:200] if text else 'N/A'}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching weather for {city}: {e}")
            logger.debug(traceback.format_exc())
            return None
    
    async def _fetch_weather(self, city: str) -> Optional[dict]:
        """Fetch and parse current weather data"""
        data = await self._fetch_raw_data(city)
        if data is None:
            return None
        return self._parse_weather_data(data, city)
    
    async def _fetch_forecast(self, city: str, days: int) -> Optional[dict]:
        """Fetch and parse forecast weather data"""
        data = await self._fetch_raw_data(city)
        if data is None:
            return None
        return self._parse_forecast_data(data, city, days)
    
    def _parse_weather_data(self, data: dict, city: str) -> Optional[dict]:
        """
        Parse and normalize current weather data from API response
        
        Args:
            data: Raw JSON response from API
            city: City name for the query
            
        Returns:
            dict with normalized weather data or None if parsing fails
        """
        try:
            current = data.get("current_condition", [])
            if not current:
                logger.warning(f"No current_condition in weather data for {city}")
                return None
            
            cur = current[0]
            nearest_area = data.get("nearest_area", [{}])[0]
            
            # Extract area information
            area_name = nearest_area.get("areaName", [{}])[0].get("value", city)
            country = nearest_area.get("country", [{}])[0].get("value", "")
            
            # Build location string
            location = f"{area_name}, {country}" if country else area_name
            
            return {
                "city": location,
                "description": cur.get("weatherDesc", [{}])[0].get("value", "未知"),
                "temp_c": cur.get("temp_C", "--"),
                "feels_like_c": cur.get("FeelsLikeC", "--"),
                "humidity": cur.get("humidity", "--"),
                "wind_speed": cur.get("windspeedKmph", cur.get("windspeedKm/h", "--")),
                "wind_dir": cur.get("winddir16Point", ""),
                "visibility": cur.get("visibility", "--"),
                "pressure": cur.get("pressure", "--"),
                "observation_time": cur.get("observation_time", ""),
            }
            
        except Exception as e:
            logger.error(f"Error parsing weather data for {city}: {e}")
            logger.debug(traceback.format_exc())
            return None
    
    def _parse_forecast_data(self, data: dict, city: str, days: int) -> Optional[dict]:
        """
        Parse and normalize forecast data from API response
        
        Args:
            data: Raw JSON response from API
            city: City name for the query
            days: Number of days to include in forecast
            
        Returns:
            dict with normalized forecast data or None if parsing fails
        """
        try:
            nearest_area = data.get("nearest_area", [{}])[0]
            area_name = nearest_area.get("areaName", [{}])[0].get("value", city)
            country = nearest_area.get("country", [{}])[0].get("value", "")
            location = f"{area_name}, {country}" if country else area_name
            
            weather_list = data.get("weather", [])
            if not weather_list:
                logger.warning(f"No weather forecast data for {city}")
                return None
            
            forecast_days = []
            # weather_list[0] is today, [1] is tomorrow, etc.
            # If days=1, we only want tomorrow (index 1)
            # If days=3, we want today+tomorrow+day after (indices 0,1,2)
            for i in range(min(days, len(weather_list))):
                day_data = weather_list[i]
                hourly = day_data.get("hourly", [])
                
                # Pick midday weather as representative (around 12:00 or 15:00)
                representative = None
                for h in hourly:
                    time_str = h.get("time", "")
                    if time_str in ("1200", "1500", "900"):
                        representative = h
                        break
                
                # Fallback to first available hour if midday not found
                if representative is None and hourly:
                    representative = hourly[len(hourly) // 2]
                
                # Get astronomy info
                astronomy = day_data.get("astronomy", [{}])[0]
                
                day_info = {
                    "date": day_data.get("date", ""),
                    "maxtemp_c": day_data.get("maxtempC", "--"),
                    "mintemp_c": day_data.get("mintempC", "--"),
                    "avgtemp_c": day_data.get("avgtempC", "--"),
                    "description": "",
                    "chance_of_rain": "0",
                    "wind_speed": "--",
                    "wind_dir": "",
                    "humidity": "--",
                    "uv_index": day_data.get("uvIndex", "--"),
                    "sunrise": astronomy.get("sunrise", ""),
                    "sunset": astronomy.get("sunset", ""),
                }
                
                if representative:
                    desc = representative.get("weatherDesc", [{}])[0].get("value", "未知")
                    day_info["description"] = desc
                    day_info["chance_of_rain"] = representative.get("chanceofrain", "0")
                    day_info["wind_speed"] = representative.get("windspeedKmph", "--")
                    day_info["wind_dir"] = representative.get("winddir16Point", "")
                    day_info["humidity"] = representative.get("humidity", "--")
                
                forecast_days.append(day_info)
            
            return {
                "city": location,
                "days": len(forecast_days),
                "forecast": forecast_days,
            }
            
        except Exception as e:
            logger.error(f"Error parsing forecast data for {city}: {e}")
            logger.debug(traceback.format_exc())
            return None
    
    def _format_weather(self, data: dict) -> str:
        """
        Format current weather data into a readable string
        
        Args:
            data: Normalized weather data dict
            
        Returns:
            Formatted weather string
        """
        wind_info = f"{data['wind_speed']} km/h"
        if data.get('wind_dir'):
            wind_info += f" {data['wind_dir']}"
        
        return (
            f"🌍 地点: {data['city']}\n"
            f"🌤 天气: {data['description']}\n"
            f"🌡 温度: {data['temp_c']}°C (体感 {data['feels_like_c']}°C)\n"
            f"💧 湿度: {data['humidity']}%\n"
            f"💨 风速: {wind_info}\n"
            f"👁 能见度: {data['visibility']} km\n"
            f"🔽 气压: {data['pressure']} hPa\n"
            f"⏰ 观测时间: {data['observation_time']}"
        )
    
    def _format_forecast(self, data: dict) -> str:
        """
        Format forecast data into a readable string
        
        Args:
            data: Normalized forecast data dict
            
        Returns:
            Formatted forecast string
        """
        lines = [f"📍 {data['city']} 天气预报"]
        lines.append("=" * 24)
        
        for i, day in enumerate(data['forecast']):
            # Determine day label
            if i == 0:
                day_label = "今天"
            elif i == 1:
                day_label = "明天"
            elif i == 2:
                day_label = "后天"
            else:
                day_label = f"第{i+1}天"
            
            date_str = day['date']
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
                date_str = f"{dt.month}/{dt.day} {weekday}"
            except Exception:
                pass
            
            desc = day['description'].strip()
            rain_info = ""
            if day.get('chance_of_rain') and str(day['chance_of_rain']) != "0":
                rain_info = f" 🌧 降雨概率: {day['chance_of_rain']}%"
            
            wind_info = ""
            if day.get('wind_speed') and day['wind_speed'] != "--":
                wind_info = f" 💨 {day['wind_speed']} km/h"
                if day.get('wind_dir'):
                    wind_info += f" {day['wind_dir']}"
            
            humidity_info = ""
            if day.get('humidity') and day['humidity'] != "--":
                humidity_info = f" 💧 湿度: {day['humidity']}%"
            
            lines.append(
                f"\n📅 {day_label} ({date_str})\n"
                f"🌤 天气: {desc}{rain_info}\n"
                f"🌡 温度: {day['mintemp_c']}°C ~ {day['maxtemp_c']}°C (平均 {day['avgtemp_c']}°C)\n"
                f"{humidity_info}{wind_info}"
            )
            
            if day.get('sunrise') and day.get('sunset'):
                lines.append(f"🌅 日出: {day['sunrise']}  🌇 日落: {day['sunset']}")
        
        return "\n".join(lines)
    
    async def terminate(self):
        """Cleanup hook - called when plugin unloads"""
        logger.info("天气插件已卸载")
