#!/usr/bin/env python3
"""HTTP bridge server: exposes Cookidoo MCP tools via REST API for the web UI."""

import asyncio
import json
import os
import re

import aiohttp
from aiohttp import web
from cookidoo_api import Cookidoo, CookidooConfig, CookidooLocalizationConfig

# Global session
cd_session: aiohttp.ClientSession | None = None
cd: Cookidoo | None = None

# Algolia credentials cache
algolia_cache = {"app_id": None, "api_key": None, "index": None, "valid_until": 0}

async def get_algolia_credentials(country="de", language="de-DE"):
    """Fetch Algolia credentials from Cookidoo website."""
    import time

    # Return cached if still valid
    if algolia_cache["api_key"] and algolia_cache["valid_until"] > time.time():
        return algolia_cache

    config_url = f"https://cookidoo.{country}/search/{language}?context=recipes&countries={country}&query=test"

    async with aiohttp.ClientSession() as session:
        async with session.get(config_url) as resp:
            html = await resp.text()
            next_data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>([^<]+)</script>', html)
            if not next_data_match:
                raise Exception("Could not find Algolia config")

            data = json.loads(next_data_match.group(1))
            props = data['props']['pageProps']

            algolia_cache["app_id"] = props['algoliaAppId']
            algolia_cache["api_key"] = props['algoliaApiKeyData']['apiKey']
            algolia_cache["valid_until"] = props['algoliaApiKeyData']['validUntil']
            algolia_cache["index"] = props['algoliaIndices']['recipes']['relevance']

            return algolia_cache

# --- Tool implementations (mirroring MCP tools) ---

TOOL_MAP = {}

def tool(name):
    def decorator(fn):
        TOOL_MAP[name] = fn
        return fn
    return decorator

@tool("search_recipes")
async def search_recipes(args):
    """Search recipes via Algolia API."""
    query = args.get("query", "")
    page = args.get("page", 0)
    hits_per_page = args.get("hits_per_page", 20)

    # Get country from Cookidoo config if available
    country = "de"
    if cd and cd.localization:
        country = cd.localization.country_code.lower()

    creds = await get_algolia_credentials(country)

    algolia_url = f"https://{creds['app_id']}-dsn.algolia.net/1/indexes/{creds['index']}/query"
    headers = {
        "X-Algolia-Application-Id": creds["app_id"],
        "X-Algolia-API-Key": creds["api_key"],
        "Content-Type": "application/json"
    }
    payload = {
        "query": query,
        "page": page,
        "hitsPerPage": hits_per_page,
        "filters": f"countries:{country}"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(algolia_url, headers=headers, json=payload) as resp:
            result = await resp.json()

            # Format results
            recipes = []
            for hit in result.get('hits', []):
                recipes.append({
                    "id": hit.get("id"),
                    "title": hit.get("title"),
                    "totalTime": hit.get("totalTime"),
                    "difficulty": hit.get("difficulty"),
                    "rating": hit.get("rating"),
                    "servings": hit.get("servings"),
                })

            return {
                "recipes": recipes,
                "totalHits": result.get("nbHits", 0),
                "page": result.get("page", 0),
                "totalPages": result.get("nbPages", 0)
            }

@tool("get_recipe_details")
async def get_recipe_details(args):
    details = await cd.get_recipe_details(args["recipe_id"])
    return to_dict(details)

@tool("get_managed_collections")
async def get_managed_collections(args):
    result = await cd.get_managed_collections()
    return to_dict(result)

@tool("add_recipe_to_collection")
async def add_recipe_to_collection(args):
    return await cd.add_recipes_to_custom_collection(args["collection_id"], [args["recipe_id"]])

def to_dict(obj):
    """Convert Pydantic model or other objects to dict."""
    if obj is None:
        return None
    if hasattr(obj, 'model_dump'):
        return obj.model_dump()
    if hasattr(obj, 'dict'):
        return obj.dict()
    if hasattr(obj, '__dict__'):
        # Fallback for objects with __dict__
        return {k: to_dict(v) for k, v in obj.__dict__.items() if not k.startswith('_')}
    if isinstance(obj, list):
        return [to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj

@tool("get_shopping_list")
async def get_shopping_list(args):
    # Get actual ingredient items to buy (not just recipes)
    result = await cd.get_ingredient_items()
    items = to_dict(result)

    # Deduplicate by ID (same ID twice = API bug, different IDs with same name = legitimate)
    if isinstance(items, list):
        seen_ids = set()
        unique_items = []
        for item in items:
            item_id = item.get('id')
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                unique_items.append(item)
            elif not item_id:
                # No ID, include anyway
                unique_items.append(item)
        return unique_items
    return items

@tool("add_recipes_to_shopping_list")
async def add_recipes_to_shopping_list(args):
    return await cd.add_ingredient_items_for_recipes(args["recipe_ids"])

@tool("get_planned_recipes")
async def get_planned_recipes(args):
    # Get recipes for a calendar week (pass a date within that week)
    return await cd.get_recipes_in_calendar_week(args["start_date"])

@tool("import_web_recipe")
async def import_web_recipe(args):
    return await cd.add_custom_recipe_from(url=args["url"])

# --- HTTP handlers ---

async def handle_connect(request):
    global cd_session, cd
    try:
        body = await request.json()
        if cd_session:
            await cd_session.close()
        cd_session = aiohttp.ClientSession()
        cfg = CookidooConfig(
            email=body["email"],
            password=body["password"],
            localization=CookidooLocalizationConfig(
                country_code=body.get("country", "DE"),
                language=body.get("language", "de-DE"),
            ),
        )
        cd = Cookidoo(cd_session, cfg)
        await cd.login()
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_mcp_call(request):
    body = await request.json()
    tool_name = body["tool"]
    args = body.get("arguments", {})
    if tool_name not in TOOL_MAP:
        return web.json_response({"error": f"Unknown tool: {tool_name}"}, status=400)
    try:
        result = await TOOL_MAP[tool_name](args)
        return web.json_response({"results": result}, dumps=lambda x: json.dumps(x, default=str))
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_index(request):
    return web.FileResponse("index.html")

# --- App setup ---

app = web.Application()
app.router.add_post("/connect", handle_connect)
app.router.add_post("/mcp/call", handle_mcp_call)
app.router.add_get("/", handle_index)

# CORS middleware
@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        resp = web.Response()
    else:
        resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

app.middlewares.append(cors_middleware)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8080)
