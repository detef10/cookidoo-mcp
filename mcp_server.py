#!/usr/bin/env python3
"""MCP Server for Cookidoo (Thermomix recipe platform)."""

import asyncio
import json
import os
import logging
from typing import Any

import aiohttp
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import run_server

from cookidoo_api import Cookidoo, CookidooConfig, CookidooLocalizationConfig

logger = logging.getLogger(__name__)

# --- Cookidoo Session Management ---

class CookidooSession:
    """Manages a persistent Cookidoo API session."""

    def __init__(self):
        self.cookidoo: Cookidoo | None = None
        self.session: aiohttp.ClientSession | None = None
        self._authenticated = False

    async def ensure_connected(self):
        if self._authenticated and self.cookidoo:
            return
        email = os.environ.get("COOKIDOO_EMAIL", "")
        password = os.environ.get("COOKIDOO_PASSWORD", "")
        country = os.environ.get("COOKIDOO_COUNTRY", "DE")
        language = os.environ.get("COOKIDOO_LANGUAGE", "de-DE")

        if not email or not password:
            raise ValueError("COOKIDOO_EMAIL and COOKIDOO_PASSWORD env vars required")

        self.session = aiohttp.ClientSession()
        cfg = CookidooConfig(
            email=email,
            password=password,
            localization=CookidooLocalizationConfig(
                country_code=country,
                language=language,
            ),
        )
        self.cookidoo = Cookidoo(self.session, cfg)
        await self.cookidoo.login()
        self._authenticated = True

    async def close(self):
        if self.session:
            await self.session.close()


cookidoo_session = CookidooSession()

# --- MCP Server Definition ---

app = Server("cookidoo-mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_recipes",
            description="Search for recipes on Cookidoo by query string.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for recipes"},
                    "page": {"type": "integer", "description": "Page number (0-indexed)", "default": 0},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_recipe_details",
            description="Get full details of a specific recipe by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "recipe_id": {"type": "string", "description": "The Cookidoo recipe ID"},
                },
                "required": ["recipe_id"],
            },
        ),
        Tool(
            name="get_managed_collections",
            description="Get the user's recipe collections / lists.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="add_recipe_to_collection",
            description="Add a recipe to one of the user's collections.",
            inputSchema={
                "type": "object",
                "properties": {
                    "recipe_id": {"type": "string", "description": "Recipe ID to add"},
                    "collection_id": {"type": "string", "description": "Target collection ID"},
                },
                "required": ["recipe_id", "collection_id"],
            },
        ),
        Tool(
            name="get_shopping_list",
            description="Get the current shopping list items.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="add_recipes_to_shopping_list",
            description="Add recipe ingredients to the shopping list.",
            inputSchema={
                "type": "object",
                "properties": {
                    "recipe_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of recipe IDs to add to shopping list",
                    },
                },
                "required": ["recipe_ids"],
            },
        ),
        Tool(
            name="get_planned_recipes",
            description="Get recipes planned on the meal planner / calendar.",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                    "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                },
                "required": ["start_date", "end_date"],
            },
        ),
        Tool(
            name="import_web_recipe",
            description="Import a recipe from a URL into Cookidoo as a custom recipe.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL of the recipe to import"},
                    "name": {"type": "string", "description": "Custom name for the recipe (optional)"},
                },
                "required": ["url"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        await cookidoo_session.ensure_connected()
        cd = cookidoo_session.cookidoo

        if name == "search_recipes":
            results = await cd.search_recipes(
                arguments["query"],
                page=arguments.get("page", 0),
            )
            return [TextContent(type="text", text=json.dumps(results, default=str, indent=2))]

        elif name == "get_recipe_details":
            recipe = await cd.get_recipe_details(arguments["recipe_id"])
            return [TextContent(type="text", text=json.dumps(recipe, default=str, indent=2))]

        elif name == "get_managed_collections":
            collections = await cd.get_managed_collections()
            return [TextContent(type="text", text=json.dumps(collections, default=str, indent=2))]

        elif name == "add_recipe_to_collection":
            result = await cd.add_recipes_to_collection(
                arguments["collection_id"],
                [arguments["recipe_id"]],
            )
            return [TextContent(type="text", text=json.dumps(result, default=str, indent=2))]

        elif name == "get_shopping_list":
            items = await cd.get_shopping_list_recipes()
            return [TextContent(type="text", text=json.dumps(items, default=str, indent=2))]

        elif name == "add_recipes_to_shopping_list":
            result = await cd.add_shopping_list_recipes(arguments["recipe_ids"])
            return [TextContent(type="text", text=json.dumps(result, default=str, indent=2))]

        elif name == "get_planned_recipes":
            planned = await cd.get_planned_recipes(
                arguments["start_date"],
                arguments["end_date"],
            )
            return [TextContent(type="text", text=json.dumps(planned, default=str, indent=2))]

        elif name == "import_web_recipe":
            result = await cd.add_custom_recipe(
                url=arguments["url"],
                name=arguments.get("name"),
            )
            return [TextContent(type="text", text=json.dumps(result, default=str, indent=2))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.exception("Tool call failed")
        return [TextContent(type="text", text=f"Error: {e}")]


async def main():
    await run_server(app)

if __name__ == "__main__":
    asyncio.run(main())
