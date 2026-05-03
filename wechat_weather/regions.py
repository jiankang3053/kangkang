# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import requests


REGIONS_FILE = "regions_level.json"
DEFAULT_REGION_CODE = "421221"
DEFAULT_ADDRESS_PATH = ["湖北省", "咸宁市", "嘉鱼县"]


def _data_path() -> Path:
    return Path(__file__).with_name(REGIONS_FILE)


def _load_raw_regions() -> list[dict[str, Any]]:
    data = json.loads(_data_path().read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("全国地址数据格式不正确。")
    return data


def _normalize_city_children(province: dict[str, Any]) -> list[dict[str, Any]]:
    children = province.get("children") or []
    if not children:
        return []
    first = children[0]
    # Direct-admin municipalities in this dataset put districts directly below
    # the province node. The UI still needs province -> city -> district.
    if first.get("area") and not first.get("city"):
        return [
            {
                "code": province.get("code"),
                "name": province.get("name"),
                "children": [
                    {
                        "code": child.get("code"),
                        "name": child.get("name"),
                        "children": [],
                    }
                    for child in children
                ],
            }
        ]
    return [
        {
            "code": city.get("code"),
            "name": city.get("name"),
            "children": [
                {
                    "code": area.get("code"),
                    "name": area.get("name"),
                    "children": [],
                }
                for area in (city.get("children") or [])
            ],
        }
        for city in children
    ]


def regions_tree() -> list[dict[str, Any]]:
    return [
        {
            "code": province.get("code"),
            "name": province.get("name"),
            "children": _normalize_city_children(province),
        }
        for province in _load_raw_regions()
    ]


def _walk_leaves() -> list[dict[str, Any]]:
    leaves: list[dict[str, Any]] = []
    for province in regions_tree():
        province_name = str(province.get("name") or "")
        for city in province.get("children", []):
            city_name = str(city.get("name") or "")
            areas = city.get("children") or []
            if not areas:
                path = [province_name, city_name]
                leaves.append(
                    {
                        "code": str(city.get("code") or province.get("code") or ""),
                        "name": city_name or province_name,
                        "address_path": _clean_path(path),
                    }
                )
                continue
            for area in areas:
                path = [province_name, city_name, str(area.get("name") or "")]
                leaves.append(
                    {
                        "code": str(area.get("code") or city.get("code") or ""),
                        "name": str(area.get("name") or city_name or province_name),
                        "address_path": _clean_path(path),
                    }
                )
    return leaves


def _clean_path(parts: list[str]) -> list[str]:
    result: list[str] = []
    for value in parts:
        text = str(value or "").strip()
        if text and (not result or result[-1] != text):
            result.append(text)
    return result


def format_address_path(parts: list[str]) -> str:
    return " / ".join(_clean_path(parts))


def find_region(code: str | None) -> dict[str, Any] | None:
    if not code:
        return None
    target = str(code)
    for leaf in _walk_leaves():
        if leaf["code"] == target:
            item = deepcopy(leaf)
            item["display_name"] = format_address_path(item["address_path"])
            return item
    return None


def find_region_by_name(name: str | None) -> dict[str, Any] | None:
    if not name:
        return None
    text = str(name).strip()
    if not text:
        return None
    candidates = search_regions(text, limit=20)
    exact = next((item for item in candidates if item["name"] == text), None)
    return exact or (candidates[0] if candidates else None)


def search_regions(query: str, limit: int = 20) -> list[dict[str, Any]]:
    text = str(query or "").strip().lower()
    if not text:
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for leaf in _walk_leaves():
        display = format_address_path(leaf["address_path"])
        haystack = f"{display} {leaf['name']} {leaf['code']}".lower()
        if text not in haystack:
            continue
        score = 30
        if leaf["name"].lower() == text:
            score = 0
        elif display.lower().endswith(text):
            score = 5
        elif leaf["name"].lower().startswith(text):
            score = 10
        elif display.lower().startswith(text):
            score = 15
        item = deepcopy(leaf)
        item["display_name"] = display
        item["source"] = "china_regions"
        scored.append((score, item))
    scored.sort(key=lambda pair: (pair[0], len(pair[1]["display_name"]), pair[1]["code"]))
    return [item for _, item in scored[:limit]]


def normalize_region_payload(location: dict[str, Any]) -> dict[str, Any]:
    region = find_region(location.get("region_code"))
    if region is None and location.get("address_path"):
        path = _clean_path([str(item) for item in location.get("address_path") or []])
        region = next((item for item in _walk_leaves() if item["address_path"] == path), None)
        if region:
            region = {**region, "display_name": format_address_path(region["address_path"])}
    if region is None:
        region = find_region_by_name(location.get("name"))
    if region is None:
        name = str(location.get("name") or "").strip()
        path = _clean_path([str(item) for item in location.get("address_path") or []])
        if not name and path:
            name = path[-1]
        if not name:
            raise ValueError("请先从全国地址中选择省/市/区县。")
        return {
            "region_code": str(location.get("region_code") or ""),
            "name": name,
            "address_path": path or [name],
            "display_name": format_address_path(path or [name]),
        }
    return {
        "region_code": region["code"],
        "name": region["name"],
        "address_path": list(region["address_path"]),
        "display_name": region["display_name"],
    }


def resolve_region_coordinates(
    location: dict[str, Any],
    *,
    timeout_seconds: float = 12,
) -> dict[str, Any]:
    normalized = normalize_region_payload(location)
    if location.get("latitude") is not None and location.get("longitude") is not None:
        return {
            **normalized,
            "latitude": float(location["latitude"]),
            "longitude": float(location["longitude"]),
            "geocode_source": str(location.get("source") or "existing-coordinates"),
        }

    query = " ".join(normalized["address_path"])
    failures: list[str] = []
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": query,
                "format": "jsonv2",
                "limit": 3,
                "accept-language": "zh-CN",
            },
            headers={"User-Agent": "KangkangWeather/2.4.3"},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        for item in response.json():
            lat = item.get("lat")
            lon = item.get("lon")
            if lat is not None and lon is not None:
                return {
                    **normalized,
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "geocode_source": "nominatim",
                }
    except Exception as exc:
        failures.append(f"nominatim: {exc}")

    raise ValueError(f"无法解析「{normalized['display_name']}」的天气坐标：{'; '.join(failures) or '没有结果'}")
