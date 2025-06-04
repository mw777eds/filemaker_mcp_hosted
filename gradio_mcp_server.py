import os
import requests
import gradio as gr
from dotenv import load_dotenv
import json
from typing import Any, Dict, Callable, List
import sys
import time
from urllib.parse import urlencode

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

# Authenticate and get token
def get_fm_token():
    log_info("Attempting to get FileMaker token...")
    start_time = time.time()
    url = f"https://{FM_HOST}/fmi/data/v1/databases/{FM_DATABASE}/sessions"
    try:
        response = requests.post(
            url,
            auth=(FM_USERNAME, FM_PASSWORD),
            headers={"Content-Type": "application/json"},
            json={}
        )
        response.raise_for_status()
        token = response.json()['response']['token']
        log_info(f"FileMaker token obtained successfully in {time.time() - start_time:.2f} seconds.")
        return token
    except requests.exceptions.RequestException as e:
        log_error(f"Error getting FileMaker token after {time.time() - start_time:.2f} seconds: {e}")
        raise # Re-raise the exception

# Call a FileMaker script
def call_filemaker_script(script_name, params):
    log_info(f"Attempting to call FileMaker script: {script_name}...")
    start_time = time.time()
    try:
        token = get_fm_token()
        url = f"https://{FM_HOST}/fmi/data/v1/databases/{FM_DATABASE}/layouts/{FM_LAYOUT}/script/{script_name}"
        if params:
            # FileMaker expects script parameters as a single JSON string in the 'script.param' query parameter
            query_params = urlencode({'script.param': json.dumps(params)})
            url = f"{url}?{query_params}"

        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        result = response.json()['response']
        log_info(f"FileMaker script {script_name} called successfully in {time.time() - start_time:.2f} seconds.")
        if 'scriptResult' in result:
            try:
                return json.loads(result['scriptResult'])
            except Exception:
                return result['scriptResult']
        return result
    except requests.exceptions.RequestException as e:
        log_error(f"Error calling FileMaker script {script_name} after {time.time() - start_time:.2f} seconds: {e}")
        raise

# Fetch tool list from FileMaker
def get_tools_from_filemaker() -> list:
    log_info("Attempting to fetch tool list from FileMaker...")
    start_time = time.time()
    try:
        token = get_fm_token()
        url = f"https://{FM_HOST}/fmi/data/v1/databases/{FM_DATABASE}/layouts/{FM_LAYOUT}/script/GetToolList"
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        result = response.json()['response']
        log_info(f"Raw FileMaker response: {json.dumps(result, indent=2)}")
        script_result = json.loads(result['scriptResult'])
        tools = script_result.get('tools', [])
        log_info(f"Tool list fetched successfully in {time.time() - start_time:.2f} seconds. Found {len(tools)} tools.")
        # Log the names of all tools found
        tool_names = [tool.get('function', {}).get('name', 'unknown') for tool in tools]
        log_info(f"Tools found: {', '.join(tool_names)}")
        return tools
    except requests.exceptions.RequestException as e:
        log_error(f"Error fetching tool list from FileMaker after {time.time() - start_time:.2f} seconds: {e}")
        raise

def create_gradio_function(tool_data: Dict[str, Any]) -> Callable:
    """Create a Gradio-compatible function from tool metadata."""
    function = tool_data['function']
    name = function['name']
    description = function.get('description', '')
    parameters = function.get('parameters', {})
    properties = parameters.get('properties', {})
    required = parameters.get('required', [])

    log_info(f"Creating Gradio function for {name} with parameters: {list(properties.keys())}")

    # Build the function signature with proper type hints
    def create_function():
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

    # Create and return the function
    tool_function = create_function()
    log_info(f"Successfully created Gradio function for {name}")
    return tool_function

def setup_gradio_interface():
    """Setup Gradio interface with dynamic FileMaker tools"""
    log_info("Starting tool setup...")
    tools_data = get_tools_from_filemaker()
    log_info(f"Retrieved {len(tools_data)} tools from FileMaker")

    # Store functions for Gradio interface creation
    tool_functions = {}
    
    # Create functions for each tool
    for tool_data in tools_data:
        try:
            tool_name = tool_data['function']['name']
            log_info(f"Creating Gradio function: {tool_name}")
            
            # Create the Gradio-compatible function
            tool_func = create_gradio_function(tool_data)
            tool_functions[tool_name] = (tool_func, tool_data)
            log_info(f"Successfully created Gradio function for {tool_name}")
            
        except Exception as e:
            import traceback
            log_error(f"Error creating function {tool_data.get('function', {}).get('name', 'unknown')}: {e}")
            log_error(f"Traceback: {traceback.format_exc()}")
            continue

    # Create Gradio interface using gr.Interface for each tool
    interfaces = []
    for tool_name, (tool_func, tool_data) in tool_functions.items():
        function = tool_data['function']
        description = function.get('description', '')
        parameters = function.get('parameters', {})
        properties = parameters.get('properties', {})
        
        # Create input components
        inputs = []
        for param_name, param_info in properties.items():
            param_type = param_info.get('type', 'string')
            param_desc = param_info.get('description', '')
            
            if param_type == 'string':
                inputs.append(gr.Textbox(label=f"{param_name}", placeholder=param_desc))
            elif param_type in ['number', 'integer']:
                inputs.append(gr.Number(label=f"{param_name}", info=param_desc))
            elif param_type == 'boolean':
                inputs.append(gr.Checkbox(label=f"{param_name}", info=param_desc))
            else:
                inputs.append(gr.Textbox(label=f"{param_name}", placeholder=param_desc))
        
        # Create interface for this tool
        interface = gr.Interface(
            fn=tool_func,
            inputs=inputs,
            outputs=gr.Textbox(label="Result"),
            title=tool_name,
            description=description
        )
        interfaces.append(interface)
    
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
        # Fallback if no tools found
        demo = gr.Interface(
            fn=lambda: "No tools available",
            inputs=[],
            outputs=gr.Textbox(label="Status"),
            title="FileMaker MCP Tools"
        )
    
    return demo

def main():
    """Main function to run the server"""
    try:
        # Setup Gradio interface with MCP support
        log_info("Setting up Gradio interface with MCP support...")
        demo = setup_gradio_interface()
        
        # Launch Gradio with MCP server enabled
        log_info("Starting Gradio server with MCP support...")
        
        # Try different ports if the default is busy
        ports_to_try = [7860, 7861, 7862, 7863, 7864]
        
        for port in ports_to_try:
            try:
                log_info(f"Attempting to start server on port {port}...")
                demo.launch(
                    server_port=port,
                    mcp_server=True,
                    share=False,
                    prevent_thread_lock=False
                )
                break
            except OSError as e:
                if "Address already in use" in str(e) or "Cannot find empty port" in str(e):
                    log_info(f"Port {port} is busy, trying next port...")
                    continue
                else:
                    raise
        else:
            raise OSError("Could not find an available port in range 7860-7864")

    except Exception as e:
        import traceback
        log_error("Server crashed during launch: " + str(e))
        log_error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
