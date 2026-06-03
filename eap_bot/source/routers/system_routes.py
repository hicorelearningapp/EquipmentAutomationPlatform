from fastapi import APIRouter, Request, HTTPException

class SystemAPI:
    def __init__(self):
        self.router = APIRouter(tags=["System"])
        
        @self.router.get("/EndpointInfo")
        def get_endpoint_info(request: Request, endpoint_path: str):
            """
            Returns the required parameters and payload structure for a given API endpoint.
            Example endpoint_path: /GenerateReports/{project_id}
            """
            schema = request.app.openapi()
            paths = schema.get("paths", {})
            
            # Allow for exact match or missing leading slash
            if endpoint_path not in paths:
                if f"/{endpoint_path}" in paths:
                    endpoint_path = f"/{endpoint_path}"
                else:
                    raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint_path}' not found in API schema.")
                
            endpoint_data = paths[endpoint_path]
            # Grab the first HTTP method (usually GET or POST)
            method = list(endpoint_data.keys())[0]
            operation = endpoint_data[method]
            
            path_params = []
            query_params = []
            
            for param in operation.get("parameters", []):
                param_info = {
                    "Name": param.get("name"),
                    "Type": param.get("schema", {}).get("type", "string"),
                    "Required": param.get("required", False)
                }
                if param.get("in") == "path":
                    path_params.append(param_info)
                elif param.get("in") == "query":
                    query_params.append(param_info)
                    
            request_body = None
            if "requestBody" in operation:
                content = operation["requestBody"].get("content", {})
                json_content = content.get("application/json", {})
                schema_ref = json_content.get("schema", {})
                
                payload_structure = {}
                if "$ref" in schema_ref:
                    # Resolve the Pydantic schema reference
                    ref_path = schema_ref["$ref"].split("/")[-1]
                    components = schema.get("components", {}).get("schemas", {})
                    if ref_path in components:
                        props = components[ref_path].get("properties", {})
                        for prop_name, prop_details in props.items():
                            # Extract types, handle arrays, nested objects, or raw types
                            prop_type = prop_details.get("type", "unknown")
                            if prop_type == "array" and "items" in prop_details:
                                item_type = prop_details["items"].get("type", "unknown")
                                payload_structure[prop_name] = f"list[{item_type}]"
                            else:
                                payload_structure[prop_name] = prop_type
                                
                request_body = {
                    "Required": operation["requestBody"].get("required", False),
                    "PayloadStructure": payload_structure if payload_structure else schema_ref
                }
                
            return {
                "Endpoint": endpoint_path,
                "Method": method.upper(),
                "Description": operation.get("summary", ""),
                "PathParameters": path_params,
                "QueryParameters": query_params,
                "RequestBody": request_body
            }
