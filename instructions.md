# Instructions for Converting MCP Server to Web Client

## Current State Analysis

Your current `gradio_mcp_server.py` implements:
- A FastMCP server using stdio transport (for local Claude Desktop integration)
- Dynamic tool discovery from FileMaker via REST API
- Gradio web interface for human interaction
- Tools are created dynamically based on FileMaker script definitions

## Target Requirements

Based on the Hugging Face MCP Course documentation and your goals, you need to convert this to:

### 1. HTTP+SSE MCP Server
- Replace stdio transport with HTTP+SSE (Server-Sent Events)
- Use Gradio's built-in MCP server functionality (`mcp_server=True`)
- Expose MCP endpoint at: `http://your-server:port/gradio_api/mcp/sse`
- Enable JSON-RPC over HTTP+SSE for client-server communication

### 2. Web-Accessible for Claude
- Claude (or any MCP client) can connect via HTTP instead of stdio
- No need for local Claude Desktop configuration
- Accessible from anywhere via URL

### 3. Docker Deployment
- Package as Docker image for easy deployment
- Include all dependencies and environment setup
- Configurable via environment variables

## Key Changes Needed

### 1. Gradio Integration Approach
Instead of using FastMCP + Gradio separately, leverage Gradio's native MCP support:
- Convert your dynamic FileMaker tools to Gradio functions
- Use `demo.launch(mcp_server=True)` to enable both web UI and MCP server
- Let Gradio handle the HTTP+SSE transport automatically

### 2. Function Conversion Strategy
Your current approach creates dynamic functions via `exec()`. For Gradio MCP:
- Each FileMaker script becomes a Gradio-compatible function
- Functions need proper type hints and docstrings
- Gradio automatically converts these to MCP tools

### 3. Architecture Changes
```
Current: FileMaker → FastMCP (stdio) + Gradio (web)
Target:  FileMaker → Gradio Functions → Gradio MCP Server (HTTP+SSE)
```

### 4. Docker Requirements
- Base Python image
- Install dependencies (gradio[mcp], requests, python-dotenv)
- Copy application code
- Expose port (default 7860)
- Set environment variables for FileMaker connection

## Implementation Steps

1. **Refactor tool creation** - Convert from FastMCP tools to Gradio functions
2. **Update server launch** - Use `demo.launch(mcp_server=True)` 
3. **Test HTTP+SSE endpoint** - Verify `/gradio_api/mcp/sse` works
4. **Create Dockerfile** - Package for deployment
5. **Update Claude configuration** - Point to HTTP endpoint instead of stdio

## Benefits of This Approach

- **Simpler architecture** - Single Gradio app handles both UI and MCP
- **Web accessible** - No local setup required for Claude
- **Dockerizable** - Easy deployment and scaling
- **Maintained functionality** - Keep dynamic FileMaker integration
- **Standard compliance** - Uses official Gradio MCP integration

## Environment Variables Required

```env
FM_USERNAME=your_filemaker_username
FM_PASSWORD=your_filemaker_password
FM_HOST=your_filemaker_host
FM_DATABASE=your_filemaker_database
FM_LAYOUT=your_filemaker_layout
GRADIO_MCP_SERVER=True
```

## Claude Configuration (After Deployment)

**IMPORTANT**: Make sure your Gradio MCP server is running before configuring Claude!

### Step 1: Start the MCP Server
```bash
python gradio_mcp_server.py
```

Wait for the message: `🔨 MCP server (using SSE) running at: http://127.0.0.1:XXXX/gradio_api/mcp/sse`

### Step 2: Configure Claude Desktop
Instead of stdio transport, Claude will connect via HTTP:

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

**Note**: Replace `7860` with the actual port shown in your server logs if different.

### Step 3: Restart Claude Desktop
After updating the configuration, restart Claude Desktop to pick up the new MCP server.

### Troubleshooting
- Ensure the server is running and accessible at the URL
- Check that no firewall is blocking the connection
- Verify the port number matches what your server is using
- Look for any error messages in the server logs
