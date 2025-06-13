import os
import requests
import gradio as gr
from dotenv import load_dotenv
import json
from typing import Any, Dict, Callable, List
import sys
import time
from urllib.parse import urlencode
import signal
import threading

def log_info(msg):
    print(msg, file=sys.stderr)

def log_error(msg):
    print(msg, file=sys.stderr)

log_info("Attempting to launch gradio_mcp_server.py - version check")

print("Starting gradio_mcp_server.py", file=sys.stderr)

load_dotenv()

FM_USERNAME = os.getenv('FM_USERNAME')
FM_PASSWORD = os.getenv('FM_PASSWORD')
FM_HOST = os.getenv('FM_HOST')
FM_DATABASE = os.getenv('FM_DATABASE')
FM_LAYOUT = os.getenv('FM_LAYOUT')

# Token cache for FileMaker authentication
_fm_token_cache = {
    "token": None,
    "expires": 0,
    "lock": threading.Lock()
}

# Global shutdown flag
_shutdown_requested = False

def validate_environment():
    """Validate required environment variables are set"""
    required_vars = ['FM_USERNAME', 'FM_PASSWORD', 'FM_HOST', 'FM_DATABASE', 'FM_LAYOUT']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        log_error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return False
    return True

# Authenticate and get token with caching
def get_fm_token():
    current_time = time.time()
    
    # Check cache first (thread-safe)
    with _fm_token_cache["lock"]:
        if (_fm_token_cache["token"] and 
            current_time < _fm_token_cache["expires"]):
            log_info("Using cached FileMaker token")
            return _fm_token_cache["token"]
    
    log_info("Attempting to get new FileMaker token...")
    start_time = time.time()
    url = f"https://{FM_HOST}/fmi/data/v1/databases/{FM_DATABASE}/sessions"
    try:
        response = requests.post(
            url,
            auth=(FM_USERNAME, FM_PASSWORD),
            headers={"Content-Type": "application/json"},
            json={},
            timeout=30
        )
        response.raise_for_status()
        token = response.json()['response']['token']
        
        # Cache the token (FileMaker tokens typically last 15 minutes)
        with _fm_token_cache["lock"]:
            _fm_token_cache["token"] = token
            _fm_token_cache["expires"] = current_time + (14 * 60)  # 14 minutes for safety
        
        log_info(f"FileMaker token obtained and cached successfully in {time.time() - start_time:.2f} seconds.")
        return token
    except requests.exceptions.Timeout:
        log_error(f"FileMaker token request timed out after {time.time() - start_time:.2f} seconds")
        return None
    except requests.exceptions.RequestException as e:
        log_error(f"Error getting FileMaker token: {str(e)}")
        return None
    except (KeyError, json.JSONDecodeError) as e:
        log_error(f"Invalid response format from FileMaker: {str(e)}")
        return None
    except Exception as e:
        log_error(f"Unexpected error getting FileMaker token: {str(e)}")
        return None

# Call a FileMaker script
def call_filemaker_script(script_name, params):
    log_info(f"Attempting to call FileMaker script: {script_name}...")
    start_time = time.time()
    try:
        token = get_fm_token()
        if not token:
            return {"error": "Could not authenticate with FileMaker"}
            
        url = f"https://{FM_HOST}/fmi/data/v1/databases/{FM_DATABASE}/layouts/{FM_LAYOUT}/script/{script_name}"
        if params:
            try:
                # FileMaker expects script parameters as a single JSON string in the 'script.param' query parameter
                query_params = urlencode({'script.param': json.dumps(params)})
                url = f"{url}?{query_params}"
            except (TypeError, ValueError) as e:
                log_error(f"Error encoding script parameters: {str(e)}")
                return {"error": f"Invalid script parameters: {str(e)}"}

        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60
        )
        response.raise_for_status()
        result = response.json()['response']
        log_info(f"FileMaker script {script_name} called successfully in {time.time() - start_time:.2f} seconds.")
        
        if 'scriptResult' in result:
            try:
                return json.loads(result['scriptResult'])
            except (json.JSONDecodeError, TypeError):
                return result['scriptResult']
        return result
        
    except requests.exceptions.Timeout:
        log_error(f"FileMaker script {script_name} timed out after {time.time() - start_time:.2f} seconds")
        return {"error": f"Script {script_name} timed out"}
    except requests.exceptions.RequestException as e:
        log_error(f"Error calling FileMaker script {script_name}: {str(e)}")
        return {"error": f"Script execution failed: {str(e)}"}
    except (KeyError, json.JSONDecodeError) as e:
        log_error(f"Invalid response format from FileMaker script {script_name}: {str(e)}")
        return {"error": f"Invalid response format: {str(e)}"}
    except Exception as e:
        log_error(f"Unexpected error calling FileMaker script {script_name}: {str(e)}")
        return {"error": f"Unexpected error: {str(e)}"}

# Fetch tool list from FileMaker
def get_tools_from_filemaker() -> list:
    log_info("Attempting to fetch tool list from FileMaker...")
    start_time = time.time()
    try:
        token = get_fm_token()
        if not token:
            log_error("Could not get FileMaker token for tool list")
            return []
            
        url = f"https://{FM_HOST}/fmi/data/v1/databases/{FM_DATABASE}/layouts/{FM_LAYOUT}/script/GetToolList"
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        response.raise_for_status()
        result = response.json()['response']
        log_info(f"Raw FileMaker response: {json.dumps(result, indent=2)}")
        
        if 'scriptResult' not in result:
            log_error("No scriptResult in FileMaker response")
            return []
            
        try:
            script_result = json.loads(result['scriptResult'])
        except (json.JSONDecodeError, TypeError) as e:
            log_error(f"Could not parse scriptResult as JSON: {str(e)}")
            return []
            
        tools = script_result.get('tools', [])
        if not isinstance(tools, list):
            log_error("Tools data is not a list")
            return []
            
        log_info(f"Tool list fetched successfully in {time.time() - start_time:.2f} seconds. Found {len(tools)} tools.")
        # Log the names of all tools found
        tool_names = [tool.get('function', {}).get('name', 'unknown') for tool in tools if isinstance(tool, dict)]
        log_info(f"Tools found: {', '.join(tool_names)}")
        return tools
        
    except requests.exceptions.Timeout:
        log_error(f"Tool list request timed out after {time.time() - start_time:.2f} seconds")
        return []
    except requests.exceptions.RequestException as e:
        log_error(f"Error fetching tool list from FileMaker: {str(e)}")
        return []
    except (KeyError, json.JSONDecodeError) as e:
        log_error(f"Invalid response format from FileMaker: {str(e)}")
        return []
    except Exception as e:
        log_error(f"Unexpected error fetching tool list: {str(e)}")
        return []

def create_gradio_function(tool_data: Dict[str, Any]) -> Callable:
    """Create a Gradio-compatible function from tool metadata."""
    try:
        # Validate tool_data structure first
        if not isinstance(tool_data, dict) or 'function' not in tool_data:
            log_error("Invalid tool data structure - missing function key")
            return None
            
        function = tool_data['function']
        if not isinstance(function, dict):
            log_error("Invalid function data structure")
            return None
            
        name = function.get('name')
        if not name or not isinstance(name, str) or not name.isidentifier():
            log_error(f"Tool missing valid name: {name}")
            return None
            
        description = function.get('description', '')
        parameters = function.get('parameters', {})
        properties = parameters.get('properties', {}) if isinstance(parameters, dict) else {}
        required = parameters.get('required', []) if isinstance(parameters, dict) else []

        log_info(f"Creating Gradio function for {name} with parameters: {list(properties.keys())}")

        # Build the function signature with proper type hints
        def create_function():
            try:
                # Build parameter list with type hints
                param_list = []
                type_mapping = {
                    'string': 'str',
                    'number': 'float', 
                    'integer': 'int',
                    'boolean': 'bool'
                }
                
                # Separate required and optional parameters
                required_params = []
                optional_params = []
                
                for param_name, param_info in properties.items():
                    if not isinstance(param_info, dict):
                        continue
                        
                    # Validate parameter name
                    if not param_name.isidentifier():
                        log_error(f"Invalid parameter name: {param_name}")
                        continue
                        
                    param_type = param_info.get('type', 'string')
                    python_type = type_mapping.get(param_type, 'str')
                    
                    if param_name in required:
                        required_params.append(f"{param_name}: {python_type}")
                    else:
                        optional_params.append(f"{param_name}: {python_type} = None")
                
                # Combine with required parameters first
                param_list = required_params + optional_params
                param_str = ", ".join(param_list)

                # Create docstring with Args section for Gradio MCP
                args_section = ""
                if properties:
                    args_section = "\n    Args:\n"
                    for param_name, param_info in properties.items():
                        if isinstance(param_info, dict):
                            param_desc = param_info.get('description', '')
                            param_type = param_info.get('type', 'string')
                            args_section += f"        {param_name} ({param_type}): {param_desc}\n"

                # Create the function code
                func_code = f'''
def {name}({param_str}) -> str:
    """{description}{args_section}
    Returns:
        str: The result from FileMaker script execution
    """
    params = {{}}
'''
                # Add parameter collection
                for param_name in properties.keys():
                    if param_name.isidentifier():
                        func_code += f"    if {param_name} is not None:\n"
                        func_code += f"        params['{param_name}'] = {param_name}\n"

                func_code += f'''
    result = call_filemaker_script("{name}", params)
    return str(result)
'''
                
                # Create the function namespace
                namespace = {'call_filemaker_script': call_filemaker_script}
                
                # Execute the function code in the namespace
                exec(func_code, namespace)
                
                return namespace[name]
                
            except Exception as e:
                log_error(f"Error in create_function for {name}: {str(e)}")
                return None

        # Create and return the function
        tool_function = create_function()
        if tool_function:
            log_info(f"Successfully created Gradio function for {name}")
        else:
            log_error(f"Failed to create Gradio function for {name}")
        return tool_function
        
    except Exception as e:
        log_error(f"Error creating function: {str(e)}")
        return None

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global _shutdown_requested
    log_info(f"Received signal {signum}, initiating graceful shutdown...")
    _shutdown_requested = True

def create_fallback_interface():
    """Create a simple interface when tools can't be loaded"""
    def show_status():
        return "FileMaker tools are currently unavailable. Please check the server logs and environment variables."
    
    return gr.Interface(
        fn=show_status,
        inputs=[],
        outputs=gr.Textbox(label="Status"),
        title="FileMaker MCP Tools - Service Unavailable"
    )

def setup_gradio_interface():
    """Setup Gradio interface with dynamic FileMaker tools"""
    log_info("Starting tool setup...")
    
    try:
        tools_data = get_tools_from_filemaker()
        log_info(f"Retrieved {len(tools_data)} tools from FileMaker")

        if not tools_data:
            log_error("No tools retrieved from FileMaker, creating fallback interface")
            return create_fallback_interface()

        # Store functions for Gradio interface creation
        tool_functions = {}
        
        # Create functions for each tool
        for tool_data in tools_data:
            try:
                if not isinstance(tool_data, dict) or 'function' not in tool_data:
                    log_error("Invalid tool data structure, skipping")
                    continue
                    
                function = tool_data.get('function', {})
                tool_name = function.get('name', 'unknown')
                log_info(f"Creating Gradio function: {tool_name}")
                
                # Create the Gradio-compatible function
                tool_func = create_gradio_function(tool_data)
                if tool_func:
                    tool_functions[tool_name] = (tool_func, tool_data)
                    log_info(f"Successfully created Gradio function for {tool_name}")
                else:
                    log_error(f"Failed to create Gradio function for {tool_name}")
                
            except Exception as e:
                tool_name = tool_data.get('function', {}).get('name', 'unknown') if isinstance(tool_data, dict) else 'unknown'
                log_error(f"Error creating function {tool_name}: {str(e)}")
                continue

        if not tool_functions:
            log_error("No valid tool functions created, creating fallback interface")
            return create_fallback_interface()

        # Create Gradio interface using gr.Interface for each tool
        interfaces = []
        for tool_name, (tool_func, tool_data) in tool_functions.items():
            try:
                function = tool_data.get('function', {})
                description = function.get('description', '')
                parameters = function.get('parameters', {})
                properties = parameters.get('properties', {}) if isinstance(parameters, dict) else {}
                
                # Create input components
                inputs = []
                for param_name, param_info in properties.items():
                    if not isinstance(param_info, dict):
                        continue
                        
                    param_type = param_info.get('type', 'string')
                    param_desc = param_info.get('description', '')
                    
                    try:
                        if param_type == 'string':
                            inputs.append(gr.Textbox(label=f"{param_name}", placeholder=param_desc))
                        elif param_type in ['number', 'integer']:
                            inputs.append(gr.Number(label=f"{param_name}", info=param_desc))
                        elif param_type == 'boolean':
                            inputs.append(gr.Checkbox(label=f"{param_name}", info=param_desc))
                        else:
                            inputs.append(gr.Textbox(label=f"{param_name}", placeholder=param_desc))
                    except Exception as e:
                        log_error(f"Error creating input for {param_name}: {str(e)}")
                        continue
                
                # Create interface for this tool
                interface = gr.Interface(
                    fn=tool_func,
                    inputs=inputs,
                    outputs=gr.Textbox(label="Result"),
                    title=tool_name,
                    description=description
                )
                interfaces.append(interface)
                
            except Exception as e:
                log_error(f"Error creating interface for {tool_name}: {str(e)}")
                continue
        
        # Create tabbed interface if multiple tools, single interface if one tool
        if len(interfaces) > 1:
            demo = gr.TabbedInterface(
                interfaces, 
                tab_names=list(tool_functions.keys()),
                title="FileMaker MCP Tools"
            )
        elif len(interfaces) == 1:
            demo = interfaces[0]
        else:
            # Fallback if no interfaces created
            log_error("No valid interfaces created, using fallback")
            demo = create_fallback_interface()
        
        return demo
        
    except Exception as e:
        log_error(f"Error in setup_gradio_interface: {str(e)}")
        return create_fallback_interface()

def main():
    """Main function to run the server"""
    try:
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Validate environment first
        if not validate_environment():
            log_error("Environment validation failed. Exiting.")
            sys.exit(1)
        
        # Setup Gradio interface with MCP support
        log_info("Setting up Gradio interface with MCP support...")
        demo = setup_gradio_interface()
        
        if not demo:
            log_error("Failed to create Gradio interface. Exiting.")
            sys.exit(1)
        
        # Launch Gradio with MCP server enabled
        log_info("Starting Gradio server with MCP support for production deployment...")
        
        # Try different ports if the default is busy
        ports_to_try = [7860, 7861, 7862, 7863, 7864]
        
        for port in ports_to_try:
            try:
                log_info(f"Attempting to start server on port {port}...")
                demo.launch(
                    server_port=port,
                    server_name="0.0.0.0",  # Listen on all interfaces for server deployment
                    mcp_server=True,
                    share=False,
                    prevent_thread_lock=False,
                    show_error=True,
                    quiet=False
                )
                log_info(f"Server successfully started on port {port}")
                break
            except OSError as e:
                if "Address already in use" in str(e) or "Cannot find empty port" in str(e):
                    log_info(f"Port {port} is busy, trying next port...")
                    continue
                else:
                    log_error(f"Error starting server on port {port}: {str(e)}")
                    continue
        else:
            log_error("Could not find an available port in range 7860-7864")
            sys.exit(1)

    except KeyboardInterrupt:
        log_info("Server shutdown requested by user (Ctrl+C)")
        sys.exit(0)
    except Exception as e:
        log_error(f"Server failed to start: {str(e)}")
        sys.exit(1)
    finally:
        log_info("Server shutdown complete")

if __name__ == "__main__":
    main()
