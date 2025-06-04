FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY gradio_mcp_server.py .
COPY .env* ./

# Expose the port Gradio runs on
EXPOSE 7860

# Set environment variable to enable MCP server
ENV GRADIO_MCP_SERVER=True

# Run the application
CMD ["python", "gradio_mcp_server.py"]
