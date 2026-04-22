"""
AstrBot Weather Plugin
A simple weather query plugin using wttr.in API (no API key required)
Supports both command-based and natural language queries
"""

from typing import Optional
import aiohttp
import json
import traceback

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger



@register(
    "astrbot_plugin_weather_counhopig",
    "counhopig",
    "AstrBot 天气查询插件，支持查询全球城市天气",
    "1.1.0"
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
        Usage: /weather <city> or /天气 <城市名>
        Example: /weather Beijing or /天气 北京
        """
        message_str = event.message_str.strip()
        parts = message_str.split(maxsplit=1)
        
        # Parse city name from message
        if len(parts) < 2:
            yield event.plain_result(
                "请输入城市名称\n使用方法: /weather <城市名> 或 /天气 <城市名>\n"
                "示例: /weather Beijing 或 /天气 北京"
            )
            return
        
        city = parts[1].strip()
        
        # Fetch weather data
        weather_data = await self._fetch_weather(city)
        
        if weather_data is None:
            yield event.plain_result(
                f"抱歉，无法获取 {city} 的天气信息。\n"
                "可能原因：城市名称错误或天气服务暂时不可用。"
            )
            return
        
        # Format and send the weather information
        result = self._format_weather(weather_data)
        yield event.plain_result(result)
    
    @filter.llm_tool(name="get_weather")
    async def get_weather_tool(self, event: AstrMessageEvent, location: str):
        '''获取指定城市的当前天气信息。

        Args:
            location(string): 城市名称，例如"北京"、"上海"、"香港"
        '''
        weather_data = await self._fetch_weather(location)
        if weather_data:
            return self._format_weather(weather_data)
        return f"抱歉，无法获取 {location} 的天气信息。请检查城市名称是否正确。"
    
    async def _fetch_weather(self, city: str) -> Optional[dict]:
        url = f"{self.base_url}/{city}"
        params = {"format": "j1"}
        
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
                    return self._parse_weather_data(data, city)
                    
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching weather for {city}: {e}")
            return None
        except TimeoutError:
            logger.error(f"Timeout fetching weather for {city}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {city}: {e}")
            logger.debug(f"Response text: {text[:200] if 'text' in locals() else 'N/A'}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching weather for {city}: {e}")
            logger.debug(traceback.format_exc())
            return None
    
    def _parse_weather_data(self, data: dict, city: str) -> Optional[dict]:
        """
        Parse and normalize weather data from API response
        
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
    
    def _format_weather(self, data: dict) -> str:
        """
        Format weather data into a readable string
        
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
    
    async def terminate(self):
        """Cleanup hook - called when plugin unloads"""
        logger.info("天气插件已卸载")
