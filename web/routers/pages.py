"""Public page routes — landing, pricing, login redirect."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return request.app.state.templates.TemplateResponse("landing.html", {"request": request})


@router.get("/pricing", response_class=HTMLResponse)
async def pricing(request: Request):
    return request.app.state.templates.TemplateResponse(
        "landing.html", {"request": request, "scroll_to": "pricing"}
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return request.app.state.templates.TemplateResponse("login.html", {"request": request})
