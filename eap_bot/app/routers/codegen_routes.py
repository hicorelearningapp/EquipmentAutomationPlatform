from fastapi import APIRouter
from app.schemas.codegen import CodeUpdateRequest, ResultUpdateRequest

class CodeGenAPI:
    def __init__(self):
        self.router = APIRouter(tags=["codegen"])
        self.register_routes()

    def register_routes(self):
        self.router.post("/UpdateCode/{project_id}")(self.update_code)
        self.router.post("/UpdateResult/{project_id}")(self.update_result)

    def update_code(self, project_id: str, body: CodeUpdateRequest):
        return {
            "ProjectID": project_id,
            "Category": body.Category,
            "Status": "success",
            "Message": f"Code updated for {body.Category}"
        }

    def update_result(self, project_id: str, body: ResultUpdateRequest):
        return {
            "ProjectID": project_id,
            "Category": body.Category,
            "Status": "success",
            "Result": body.Result
        }
