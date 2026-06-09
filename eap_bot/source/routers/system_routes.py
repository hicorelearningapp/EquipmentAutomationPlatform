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
            
            normalized_search = endpoint_path.strip("/")
            search_parts = [x for x in normalized_search.split("/") if x]
            
            matched_path = None
            
            # 1. Exact match (ignoring leading/trailing slashes)
            for p in paths:
                if p.strip("/") == normalized_search:
                    matched_path = p
                    break
            
            # 2. Match with path parameter templates (e.g. /LoadProject/{project_id} matching /LoadProject)
            if not matched_path:
                for p in paths:
                    static_prefix = p.split("/{")[0].strip("/")
                    if static_prefix == normalized_search:
                        matched_path = p
                        break
            
            # 3. Match values with template placeholders (e.g. /LoadProject/13 matching /LoadProject/{project_id})
            if not matched_path:
                for p in paths:
                    p_parts = [x for x in p.strip("/").split("/") if x]
                    if len(p_parts) == len(search_parts):
                        match = True
                        for sp, pp in zip(search_parts, p_parts):
                            if pp.startswith("{") and pp.endswith("}"):
                                continue
                            if sp != pp:
                                match = False
                                break
                        if match:
                            matched_path = p
                            break

            if not matched_path:
                raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint_path}' not found in API schema.")
            
            endpoint_path = matched_path
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
                    
            def _resolve_schema(schema_node):
                if not schema_node or not isinstance(schema_node, dict):
                    return "unknown"
                
                if "$ref" in schema_node:
                    ref_path = schema_node["$ref"].split("/")[-1]
                    components = schema.get("components", {}) or {}
                    schemas = components.get("schemas", {}) or {}
                    if ref_path in schemas:
                        return _resolve_schema(schemas[ref_path])
                    return "unknown"

                if "anyOf" in schema_node:
                    for option in schema_node["anyOf"]:
                        if isinstance(option, dict) and option.get("type") != "null":
                            return _resolve_schema(option)

                node_type = schema_node.get("type", "object")

                if node_type == "object":
                    if "properties" in schema_node:
                        result = {}
                        for prop_name, prop_details in schema_node["properties"].items():
                            result[prop_name] = _resolve_schema(prop_details)
                        return result
                    elif "additionalProperties" in schema_node:
                        return {"<key>": _resolve_schema(schema_node["additionalProperties"])}
                    else:
                        return "object"
                elif node_type == "array":
                    items_schema = schema_node.get("items", {})
                    resolved_item = _resolve_schema(items_schema)
                    return [resolved_item]
                else:
                    return node_type

            request_body = None
            if "requestBody" in operation:
                content = operation["requestBody"].get("content", {})
                json_content = content.get("application/json", {})
                schema_ref = json_content.get("schema", {})
                
                request_body = {
                    "Required": operation["requestBody"].get("required", False),
                    "PayloadStructure": _resolve_schema(schema_ref)
                }

            response_body = None
            if "responses" in operation:
                success_resp = None
                for status_code, resp_data in operation["responses"].items():
                    if status_code.startswith("2"):
                        success_resp = resp_data
                        break
                
                if success_resp:
                    content = success_resp.get("content", {})
                    json_content = content.get("application/json", {})
                    schema_ref = json_content.get("schema", {})
                    
                    response_body = {
                        "PayloadStructure": _resolve_schema(schema_ref)
                    }
                
            return {
                "Endpoint": endpoint_path,
                "Method": method.upper(),
                "Description": operation.get("summary", ""),
                "PathParameters": path_params,
                "QueryParameters": query_params,
                "RequestBody": request_body,
                "ResponseBody": response_body
            }
