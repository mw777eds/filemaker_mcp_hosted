# FileMaker MCP Server

This project implements a Model Context Protocol (MCP) server that dynamically exposes FileMaker scripts as tools. It uses Gradio with native MCP support to provide both a web interface and HTTP+SSE MCP endpoint.

## Features

- **Dynamic Tool Discovery**: Automatically discovers FileMaker scripts and exposes them as MCP tools
- **Dual Interface**: Provides both web UI (Gradio) and MCP API (HTTP+SSE) 
- **Docker Support**: Easy deployment with Docker and docker-compose
- **Web Accessible**: Claude can connect via HTTP instead of requiring local setup

## Setup

### Local Development

1.  **Clone the repository:**

    ```bash
    git clone <repository_url>
    cd mcp-server-demo
    ```

2.  **Create a virtual environment:**

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**

    Create a `.env` file in the project root with the following variables:

    ```env
    FM_USERNAME=your_filemaker_username
    FM_PASSWORD=your_filemaker_password
    FM_HOST=your_filemaker_host
    FM_DATABASE=your_filemaker_database
    FM_LAYOUT=your_filemaker_layout
    ```

    Replace the placeholder values with your actual FileMaker credentials and database details.

### Docker Deployment

1.  **Using docker-compose (recommended):**

    ```bash
    docker-compose up -d
    ```

2.  **Using Docker directly:**

    ```bash
    docker build -t filemaker-mcp .
    docker run -p 7860:7860 --env-file .env filemaker-mcp
    ```

## Running the Server

### Local Development

1.  **Activate the virtual environment** (if not already active):

    ```bash
    source venv/bin/activate
    ```

2.  **Run the server script:**

    ```bash
    python gradio_mcp_server.py
    ```

### Production (Docker)

```bash
docker-compose up -d
```

## Accessing the Server

- **Web Interface**: http://localhost:7860
- **MCP Endpoint**: http://localhost:7860/gradio_api/mcp/sse
- **API Schema**: http://localhost:7860/gradio_api/mcp/schema

## Claude Configuration

### For HTTP+SSE (Recommended)

1. **Start the MCP server first:**
   ```bash
   python gradio_mcp_server.py
   ```

2. **Note the server URL from the logs:**
   Look for: `🔨 MCP server (using SSE) running at: http://127.0.0.1:XXXX/gradio_api/mcp/sse`

3. **Add to your Claude Desktop configuration:**
   ```json
   {
     "mcpServers": {
       "filemaker-mcp": {
         "command": "npx",
         "args": [
           "mcp-remote", 
           "http://127.0.0.1:7860/gradio_api/mcp/sse"
         ]
       }
     }
   }
   ```

4. **Restart Claude Desktop** to pick up the new configuration.

### For Local Development (stdio - Legacy)

```json
{
  "mcpServers": {
    "filemaker-mcp": {
      "command": "/path/to/your/venv/bin/python3",
      "args": ["/path/to/gradio_mcp_server.py"],
      "cwd": "/path/to/project",
      "transport": "stdio"
    }
  }
}
```

### Troubleshooting Connection Issues

- Ensure the server is running before starting Claude
- Check that the port number in your config matches the server logs
- Verify no firewall is blocking the connection
- Look for error messages in both server and Claude logs

## Architecture

```
FileMaker Database → REST API → Gradio Functions → MCP Tools (HTTP+SSE)
                                      ↓
                              Web Interface (Gradio UI)
```

The server:
1. Connects to FileMaker via REST API
2. Discovers available scripts dynamically
3. Creates Gradio-compatible functions for each script
4. Exposes both web UI and MCP endpoint simultaneously
