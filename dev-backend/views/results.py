import os
from datetime import datetime
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import FileResponse,JSONResponse
from starlette.background import BackgroundTask
from module._auth import require_admin
from module._result_query import export_results_csv,query_results,result_detail,result_media_path,result_overview

api_results = APIRouter(prefix="/results",dependencies=[Depends(require_admin)])


def _filters(keyword: str = "",start_ms: int = 0,end_ms: int = 0,sop_name: str = "",camera_name: str = "",execution_status: str = "",quality_status: str = "",has_media: bool | None = None) -> dict:return {"keyword":keyword,"startMs":start_ms,"endMs":end_ms,"sopName":sop_name,"cameraName":camera_name,"executionStatus":execution_status,"qualityStatus":quality_status,"hasMedia":has_media}


@api_results.get("")
def get_results(page: int = Query(1,ge=1),page_size: int = Query(20,ge=1,le=100),keyword: str = "",start_ms: int = 0,end_ms: int = 0,sop_name: str = "",camera_name: str = "",execution_status: str = "",quality_status: str = "",has_media: bool | None = None):
    try:return JSONResponse({"status":True,"data":query_results(_filters(keyword,start_ms,end_ms,sop_name,camera_name,execution_status,quality_status,has_media),page,page_size)})
    except Exception as exc:raise HTTPException(status_code=500,detail=f"Failed to query SOP results: {exc}") from exc


@api_results.get("/overview")
def get_result_overview(keyword: str = "",start_ms: int = 0,end_ms: int = 0,sop_name: str = "",camera_name: str = "",execution_status: str = "",quality_status: str = "",has_media: bool | None = None):
    try:return JSONResponse({"status":True,"data":result_overview(_filters(keyword,start_ms,end_ms,sop_name,camera_name,execution_status,quality_status,has_media))})
    except Exception as exc:raise HTTPException(status_code=500,detail=f"Failed to load result overview: {exc}") from exc


@api_results.get("/export")
def export_result_file(keyword: str = "",start_ms: int = 0,end_ms: int = 0,sop_name: str = "",camera_name: str = "",execution_status: str = "",quality_status: str = "",has_media: bool | None = None):
    try:path,count,truncated = export_results_csv(_filters(keyword,start_ms,end_ms,sop_name,camera_name,execution_status,quality_status,has_media));filename = f"FAIVS_SOP_Results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv";return FileResponse(path,media_type="text/csv; charset=utf-8",filename=filename,headers={"X-Exported-Rows":str(count),"X-Export-Truncated":str(truncated).lower()},background=BackgroundTask(lambda: os.path.exists(path) and os.unlink(path)))
    except Exception as exc:raise HTTPException(status_code=500,detail=f"Failed to export SOP results: {exc}") from exc


@api_results.get("/{run_id}")
def get_result_detail(run_id: str):
    try:return JSONResponse({"status":True,"data":result_detail(run_id)})
    except FileNotFoundError as exc:raise HTTPException(status_code=404,detail=str(exc)) from exc
    except Exception as exc:raise HTTPException(status_code=500,detail=f"Failed to load result detail: {exc}") from exc


@api_results.get("/{run_id}/media/{media_id}")
def get_result_media(run_id: str,media_id: str,download: bool = False):
    try:path,mime_type,filename = result_media_path(run_id,media_id);return FileResponse(path,media_type=mime_type,filename=filename if download else None,headers={"Cache-Control":"private, max-age=300"})
    except FileNotFoundError as exc:raise HTTPException(status_code=404,detail=str(exc)) from exc
    except Exception as exc:raise HTTPException(status_code=500,detail=f"Failed to load result media: {exc}") from exc
