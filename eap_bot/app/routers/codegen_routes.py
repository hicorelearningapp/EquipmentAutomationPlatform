from fastapi import APIRouter, HTTPException
from app.schemas.codegen import CodeUpdateRequest, ResultUpdateRequest
from app.services.storage_service import StorageService, StorageError, ProjectNotFoundError

class CodeGenAPI:
    def __init__(self):
        self.router = APIRouter(tags=["codegen"])
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.post("/UpdateCode/{project_id}")(self.update_code)
        self.router.post("/UpdateResult/{project_id}")(self.update_result)

    def update_code(self, project_id: int, body: CodeUpdateRequest):
        try:
            self.storage.save_project_code(project_id, body.Category, body.SourceCode)
            return {
                "ProjectID": project_id,
                "Category": body.Category,
                "Status": "success",
                "Message": f"Code updated for {body.Category}"
            }
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def update_result(self, project_id: int, body: ResultUpdateRequest):
        return {
            "ProjectID": project_id,
            "Category": body.Category,
            "Status": "success",
            "Result": body.Result
        }
