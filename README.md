# Cookidoo MCP Server + Web UI

An MCP server for the Cookidoo (Thermomix) platform with a simple web interface.

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file (optional, for MCP stdio mode):
```
COOKIDOO_EMAIL=your@email.com
COOKIDOO_PASSWORD=yourpassword
```

## Usage

### Option 1: Web UI (recommended for interactive use)

```bash
python bridge_server.py
```

Open http://localhost:8080 in your browser. Enter your Cookidoo credentials and click Connect.

### Option 2: MCP stdio server (for AI assistants like Claude)

```bash
python mcp_server.py
```

Or configure in your MCP client (e.g. Claude Desktop `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "cookidoo": {
      "command": "python",
      "args": ["mcp_server.py"],
      "env": {
        "COOKIDOO_EMAIL": "your@email.com",
        "COOKIDOO_PASSWORD": "yourpassword",
        "COOKIDOO_COUNTRY": "DE",
        "COOKIDOO_LANGUAGE": "de-DE"
      }
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `search_recipes` | Search recipes by keyword |
| `get_recipe_details` | Get full recipe details by ID |
| `get_managed_collections` | List your recipe collections |
| `add_recipe_to_collection` | Add recipe to a collection |
| `get_shopping_list` | View shopping list |
| `add_recipes_to_shopping_list` | Add recipe ingredients to shopping list |
| `get_planned_recipes` | View meal planner for date range |
| `import_web_recipe` | Import a recipe from any URL |

## Credits

Built on top of the [cookidoo-api](https://github.com/miaucl/cookidoo-api) package by miaucl.
