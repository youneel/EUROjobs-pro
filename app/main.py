"""FastAPI application: pages, JSON endpoints, SSE and the assistant."""
from __future__ import annotations

import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from fastapi import Body, Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import BASE_DIR, STATIC_DIR, TEMPLATES_DIR, settings
from app.data import CAUSE_AREAS, CATEGORIES, ORG_TYPES
from app.db import get_db, init_db
from app.documents import render_docx, render_pdf, safe_filename
from app.i18n import catalog_js, is_rtl, normalize_lang, translator_for
from app.ingest import live_augment
from app.links import validate_url
from app.llm.quota import quota
from app.models import (
    ChatSession,
    ClickLog,
    Document,
    Listing,
    PushDevice,
    SavedListing,
    SourceRun,
    User,
    UserProfile,
    VolunteerDetails,
    utcnow,
)
from app.search import SearchFilters, card_dict, counter, facets, search_listings, similar_listings
from app.security import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    clean_text,
    dump_session,
    hash_password,
    load_session,
    new_session,
    rate_limit,
    valid_csrf,
    verify_password,
)
from app.utils import (
    detect_country,
    flag_url,
    html_to_text,
    prepare_description,
    region_icon,
)
from app.visa.knowledge import load_knowledge

log = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

@pass_context
def _f_date(ctx, value, fmt="medium"):
    return ctx["tr"].date(value, fmt)


@pass_context
def _f_relative(ctx, value):
    return ctx["tr"].relative(value)


@pass_context
def _f_money(ctx, amount, currency=None):
    return ctx["tr"].money(amount, currency)


@pass_context
def _f_country(ctx, code):
    return ctx["tr"].country(code)


@pass_context
def _f_number(ctx, value):
    return ctx["tr"].number(value)


templates.env.filters["ldate"] = _f_date
templates.env.filters["lrelative"] = _f_relative
templates.env.filters["lmoney"] = _f_money
templates.env.filters["lcountry"] = _f_country
templates.env.filters["lnumber"] = _f_number
templates.env.filters["flag"] = lambda code: flag_url(code) or region_icon(code)

templates.env.globals["settings"] = settings
templates.env.globals["categories"] = CATEGORIES
templates.env.globals["cause_areas"] = CAUSE_AREAS
templates.env.globals["org_types"] = ORG_TYPES


def _quota_snapshot() -> dict | None:
    if not settings.ai_enabled:
        return None
    try:
        return quota.status("fast")
    except Exception:  # pragma: no cover - counters must never break a page
        return None


def _page_url(request: Request, page: int) -> str:
    params = dict(request.query_params)
    params["page"] = str(page)
    query = "&".join(f"{k}={v}" for k, v in params.items() if v not in ("", None))
    return f"{request.url.path}?{query}"


def _identity(request: Request, user: User | None) -> str:
    if user is not None:
        return f"u{user.id}"
    vid = request.state.session.get("vid") or "anon"
    return f"v{vid}"


def _ctx(request: Request, user: User | None, **extra) -> dict[str, Any]:
    tr = request.state.translator
    lang = tr.lang
    data = {
        "request": request,
        "lang": lang,
        "rtl": is_rtl(lang),
        "t": tr.t,
        "tn": tr.tn,
        "tr": tr,
        "theme": request.state.theme,
        "csrf": request.state.session.get("csrf", ""),
        "user": user,
        "ai_enabled": settings.ai_enabled,
        "quota": _quota_snapshot(),
        "languages": settings.languages,
        "path": request.url.path,
    }
    data.update(extra)
    return data


def render(request: Request, template: str, user: User | None, status_code: int = 200, **extra) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request, name=template, context=_ctx(request, user, **extra), status_code=status_code
    )


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.state.session.get("uid")
    if not uid:
        return None
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return None
    user = db.get(User, uid)
    if user is None:
        return None
    if user.profile is None:
        user.profile = UserProfile(user_id=user.id, full_name=user.display_name or "")
        db.add(user.profile)
        db.commit()
    return user


def require_user(request: Request, user: User | None = Depends(current_user)) -> User:
    if user is None:
        target = request.url.path
        raise RedirectException(f"/auth/login?next={target}")
    return user


class RedirectException(Exception):
    def __init__(self, url: str):
        self.url = url


def check_csrf(request: Request, token: str | None) -> None:
    if not valid_csrf(request.state.session, token):
        raise HTTPException(status_code=400, detail="Invalid security token")


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler = None
    if settings.enable_scheduler:
        try:
            from app.scheduler import start_scheduler

            scheduler = start_scheduler()
        except Exception:  # pragma: no cover - scheduler is optional
            log.exception("Could not start the background scheduler")
    try:
        yield
    finally:
        if scheduler is not None:
            try:
                scheduler.shutdown(wait=False)
            except Exception:  # pragma: no cover
                pass
        from app.llm.client import llm

        await llm.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="WorkAtlas", version="2.0.0", lifespan=lifespan)
    app.mount("/assets", StaticFiles(directory=str(BASE_DIR / "assets")), name="assets")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.exception_handler(RedirectException)
    async def _redirect_handler(request: Request, exc: RedirectException):
        return RedirectResponse(exc.url, status_code=303)

    @app.middleware("http")
    async def session_middleware(request: Request, call_next):
        session = load_session(request.cookies.get(SESSION_COOKIE))
        fresh = session is None
        if session is None:
            session = new_session()
        query_lang = request.query_params.get("lang")
        accept = request.headers.get("accept-language", "")
        lang = normalize_lang(
            query_lang or request.cookies.get("ejp_lang") or session.get("locale") or accept
        )
        theme = request.cookies.get("ejp_theme") or "system"
        if theme not in {"light", "dark", "system"}:
            theme = "system"
        request.state.session = session
        request.state.lang = lang
        request.state.theme = theme
        request.state.translator = translator_for(lang)

        response = await call_next(request)

        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
        secure_cookie = (forwarded_proto or request.url.scheme) == "https"
        if fresh or session.get("locale") != lang:
            session["locale"] = lang
            response.set_cookie(
                SESSION_COOKIE,
                dump_session(session),
                max_age=SESSION_MAX_AGE,
                httponly=True,
                samesite="lax",
                secure=secure_cookie,
            )
        if query_lang:
            response.set_cookie(
                "ejp_lang", lang, max_age=SESSION_MAX_AGE, httponly=False, samesite="lax"
            )
        return response

    register_routes(app)
    return app


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def register_routes(app: FastAPI) -> None:
    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}

    @app.get("/i18n/{lang}.js")
    def i18n_js(lang: str):
        code = normalize_lang(lang)
        body = f"window.EJP_I18N={catalog_js(code)};window.EJP_LANG={json.dumps(code)};"
        return Response(body, media_type="application/javascript; charset=utf-8")

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, db: Session = Depends(get_db), user: User | None = Depends(current_user)):
        job_counts = counter(db, "job")
        volunteer_counts = counter(db, "volunteer")
        latest_jobs, _ = search_listings(db, SearchFilters(listing_type="job", page_size=6))
        latest_volunteers, _ = search_listings(
            db, SearchFilters(listing_type="volunteer", page_size=3)
        )
        return render(
            request,
            "home.html",
            user,
            job_counts=job_counts,
            volunteer_counts=volunteer_counts,
            jobs=[card_dict(row) for row in latest_jobs],
            volunteers=[card_dict(row) for row in latest_volunteers],
            country_count=len(facets(db, "job")["countries"]),
            top_countries=facets(db, "job")["countries"][:8],
        )

    @app.get("/jobs", response_class=HTMLResponse)
    def jobs_page(
        request: Request,
        db: Session = Depends(get_db),
        user: User | None = Depends(current_user),
    ):
        return _listing_page(request, db, user, "job")

    @app.get("/volunteer", response_class=HTMLResponse)
    def volunteer_page(
        request: Request,
        db: Session = Depends(get_db),
        user: User | None = Depends(current_user),
    ):
        return _listing_page(request, db, user, "volunteer")

    def _listing_page(request, db, user, kind: str):
        filters = SearchFilters.from_query(dict(request.query_params))
        filters.listing_type = kind
        rows, total = search_listings(db, filters)
        cards = [card_dict(row) for row in rows]
        saved_ids = _saved_ids(db, user)
        facet_data = facets(db, kind)
        counts = counter(db, kind)

        if request.query_params.get("partial") == "1":
            html = templates.get_template("_cards.html").render(
                **{
                    **_ctx(request, user),
                    "cards": cards,
                    "saved_ids": saved_ids,
                    "kind": kind,
                }
            )
            return JSONResponse(
                {
                    "html": html,
                    "total": total,
                    "page": filters.page,
                    "has_more": filters.page * filters.page_size < total,
                }
            )

        return render(
            request,
            "list.html",
            user,
            kind=kind,
            cards=cards,
            total=total,
            filters=filters,
            facets=facet_data,
            counts=counts,
            saved_ids=saved_ids,
            page_url=lambda p: _page_url(request, p),
            prev_url=_page_url(request, filters.page - 1) if filters.page > 1 else "",
            next_url=(
                _page_url(request, filters.page + 1)
                if filters.page * filters.page_size < total
                else ""
            ),
        )

    @app.get("/api/listings")
    def api_listings(
        request: Request, db: Session = Depends(get_db), user: User | None = Depends(current_user)
    ):
        filters = SearchFilters.from_query(dict(request.query_params))
        rows, total = search_listings(db, filters)
        return {
            "total": total,
            "page": filters.page,
            "has_more": filters.page * filters.page_size < total,
            "items": [card_dict(row) for row in rows],
        }

    @app.get("/api/live")
    async def api_live(q: str = "", type: str = "job"):
        """Live augmentation: fetch fresh matching listings without storing them."""
        query = clean_text(q, 120)
        if not query:
            return {"items": []}
        cards = await live_augment(query, limit_seconds=4.5)
        if type == "job":
            cards = [card for card in cards if card.get("type", "job") == "job"]
        return {"items": cards[:6]}

    @app.get("/api/agent/quota")
    def agent_quota(request: Request, user: User | None = Depends(current_user)):
        if not settings.ai_enabled:
            return {"enabled": False}
        remaining = quota.user_remaining(_identity(request, user))
        return {
            "enabled": True,
            "remaining": remaining,
            "quota": _quota_snapshot(),
        }

    @app.get("/api/app/config")
    def app_config(request: Request):
        """Feature flags and links consumed by the iOS shell only."""
        base = settings.public_url or str(request.base_url).rstrip("/")
        return {
            "app": "WorkAtlas",
            "latest_version": settings.app_latest_version,
            "min_supported_version": settings.app_min_version,
            "store_url": settings.app_store_url,
            "support_email": settings.support_email,
            "privacy_url": f"{base}/legal",
            "support_url": f"{base}/support",
            "push_enabled": settings.push_enabled,
            "features": {
                "biometric_lock": True,
                "native_share": True,
                "document_export": True,
                "offline_notice": True,
            },
        }

    @app.post("/api/push/register")
    def push_register(
        request: Request,
        payload: dict = Body(...),
        db: Session = Depends(get_db),
        user: User = Depends(require_user),
    ):
        check_csrf(request, str(payload.get("csrf") or ""))
        if not settings.push_enabled:
            raise HTTPException(status_code=404, detail="Push notifications are not configured")
        token = str(payload.get("token") or "").strip()
        if not re.fullmatch(r"[A-Fa-f0-9]{32,400}", token):
            raise HTTPException(status_code=400, detail="Invalid device token")
        locale = normalize_lang(str(payload.get("locale") or request.state.lang))
        row = db.scalar(select(PushDevice).where(PushDevice.token == token))
        if row is None:
            row = PushDevice(token=token, user_id=user.id, platform="ios", locale=locale)
            db.add(row)
        else:
            row.user_id = user.id
            row.locale = locale
            row.enabled = True
            row.last_seen_at = utcnow()
        db.commit()
        return {"ok": True}

    @app.post("/api/push/unregister")
    def push_unregister(
        request: Request,
        payload: dict = Body(...),
        db: Session = Depends(get_db),
        user: User = Depends(require_user),
    ):
        check_csrf(request, str(payload.get("csrf") or ""))
        token = str(payload.get("token") or "").strip()
        row = db.scalar(
            select(PushDevice).where(
                PushDevice.user_id == user.id, PushDevice.token == token
            )
        )
        if row is not None:
            db.delete(row)
            db.commit()
        return {"ok": True}

    @app.get("/.well-known/apple-app-site-association")
    def apple_app_site_association():
        if not settings.apple_team_id:
            raise HTTPException(status_code=404)
        app_id = f"{settings.apple_team_id}.{settings.ios_bundle_id}"
        return JSONResponse(
            {
                "applinks": {
                    "apps": [],
                    "details": [
                        {
                            "appID": app_id,
                            "paths": ["/jobs/*", "/volunteer/*", "/documents/*", "/tools"],
                        }
                    ],
                },
                "webcredentials": {"apps": [app_id]},
            }
        )

    @app.get("/jobs/{public_id}", response_class=HTMLResponse)
    def job_detail(
        request: Request,
        public_id: str,
        db: Session = Depends(get_db),
        user: User | None = Depends(current_user),
    ):
        return _detail(request, db, user, public_id, "job")

    @app.get("/volunteer/{public_id}", response_class=HTMLResponse)
    def volunteer_detail(
        request: Request,
        public_id: str,
        db: Session = Depends(get_db),
        user: User | None = Depends(current_user),
    ):
        return _detail(request, db, user, public_id, "volunteer")

    def _detail(request, db, user, public_id, kind):
        listing = db.scalar(select(Listing).where(Listing.public_id == public_id))
        if listing is None or listing.listing_type != kind or not listing.is_active:
            return render(request, "error.html", user, status_code=404, code=404)
        saved = False
        if user is not None:
            saved = (
                db.scalar(
                    select(SavedListing.id).where(
                        SavedListing.user_id == user.id, SavedListing.listing_id == listing.id
                    )
                )
                is not None
            )
        docs: list[Document] = []
        if user is not None:
            docs = list(
                db.scalars(
                    select(Document)
                    .where(Document.user_id == user.id, Document.listing_id == listing.id)
                    .order_by(Document.created_at.desc())
                ).all()
            )
        similar = [card_dict(row) for row in similar_listings(db, listing, 4)]
        description_html = prepare_description(listing.description_html or "")
        description_text = html_to_text(description_html or listing.description_text or "")
        reading_minutes = max(1, round(len(description_text.split()) / 220)) if description_text else 0
        return render(
            request,
            "detail.html",
            user,
            listing=listing,
            card=card_dict(listing),
            volunteer=listing.volunteer,
            saved=saved,
            similar=similar,
            documents=docs,
            kind=kind,
            description_html=description_html,
            reading_minutes=reading_minutes,
        )

    @app.get("/go/{public_id}")
    async def go(public_id: str, request: Request, db: Session = Depends(get_db)):
        listing = db.scalar(select(Listing).where(Listing.public_id == public_id))
        if listing is None or not listing.is_active:
            return render(request, "error.html", None, status_code=404, code=404)
        url = listing.apply_url_final or listing.apply_url_original or ""
        ip = request.client.host if request.client else "unknown"
        if not rate_limit(f"go:{ip}", 30, 60):
            return render(request, "error.html", None, status_code=429, code=429)
        ok, final, reason = await validate_url(url, deep=False)
        if not ok:
            listing.last_checked_at = datetime.now(timezone.utc)
            if reason.startswith("HTTP 4") or "blocked" in reason:
                listing.is_active = False
            db.commit()
            return render(
                request,
                "error.html",
                None,
                status_code=410,
                code="dead",
                apply_url=url,
                reason=reason,
                listing=listing,
            )
        if final and final != listing.apply_url_final:
            listing.apply_url_final = final
        listing.last_checked_at = datetime.now(timezone.utc)
        uid = request.state.session.get("uid")
        db.add(
            ClickLog(
                listing_id=listing.id,
                user_id=int(uid) if uid and str(uid).isdigit() else None,
                referrer=clean_text(request.headers.get("referer", ""), 480),
            )
        )
        db.commit()
        return RedirectResponse(final or url, status_code=302)

    @app.post("/saved/{public_id}")
    def toggle_saved(
        public_id: str,
        request: Request,
        csrf: str = Form(""),
        db: Session = Depends(get_db),
        user: User | None = Depends(current_user),
    ):
        check_csrf(request, csrf)
        if user is None:
            raise RedirectException(f"/auth/login?next=/jobs/{public_id}")
        listing = db.scalar(select(Listing).where(Listing.public_id == public_id))
        if listing is None:
            raise HTTPException(404)
        row = db.scalar(
            select(SavedListing).where(
                SavedListing.user_id == user.id, SavedListing.listing_id == listing.id
            )
        )
        if row is None:
            db.add(SavedListing(user_id=user.id, listing_id=listing.id))
            saved = True
        else:
            db.delete(row)
            saved = False
        db.commit()
        if request.headers.get("accept", "").startswith("application/json"):
            return {"saved": saved}
        target = f"/{'volunteer' if listing.listing_type == 'volunteer' else 'jobs'}/{listing.public_id}"
        return RedirectResponse(f"{target}?ok=common.saved", status_code=303)

    @app.get("/countries", response_class=HTMLResponse)
    def countries_page(
        request: Request, db: Session = Depends(get_db), user: User | None = Depends(current_user)
    ):
        job_facets = facets(db, "job")["countries"]
        volunteer_facets = facets(db, "volunteer")["countries"]
        return render(
            request,
            "countries.html",
            user,
            job_facets=job_facets,
            volunteer_facets=volunteer_facets,
        )

    @app.get("/visa", response_class=HTMLResponse)
    def visa_page(
        request: Request,
        db: Session = Depends(get_db),
        user: User | None = Depends(current_user),
        country: str = "",
    ):
        entries = load_knowledge()
        code = ""
        if country:
            code, _ = detect_country(country) or (country.lower()[:2], "")
        if code:
            entries = [e for e in entries if e.country in {code.lower(), "worldwide", "eu"}]
        return render(request, "visa.html", user, entries=entries, country=code)

    @app.get("/legal", response_class=HTMLResponse)
    def legal_page(request: Request, user: User | None = Depends(current_user)):
        return render(request, "legal.html", user)

    @app.get("/support", response_class=HTMLResponse)
    def support_page(request: Request, user: User | None = Depends(current_user)):
        return render(request, "support.html", user)

    @app.get("/tools", response_class=HTMLResponse)
    def tools_page(request: Request, user: User | None = Depends(current_user)):
        return render(request, "tools.html", user)

    # -- auth ---------------------------------------------------------------
    @app.get("/auth/login", response_class=HTMLResponse)
    def login_page(request: Request, user: User | None = Depends(current_user), next: str = ""):
        if user is not None:
            return RedirectResponse("/profile", status_code=303)
        return render(request, "auth.html", user, mode="login", next=next)

    @app.post("/auth/login")
    def login_submit(
        request: Request,
        email: str = Form(""),
        password: str = Form(""),
        csrf: str = Form(""),
        next: str = Form(""),
        db: Session = Depends(get_db),
    ):
        check_csrf(request, csrf)
        ip = request.client.host if request.client else "unknown"
        if not rate_limit(f"login:{ip}", 8, 300):
            return render(request, "auth.html", None, status_code=429, mode="login", error="errors.429_title")
        email = clean_text(email, 320).lower()
        user = db.scalar(select(User).where(User.email == email))
        if user is None or not verify_password(password, user.password_hash):
            return render(
                request,
                "auth.html",
                None,
                status_code=400,
                mode="login",
                error="auth.invalid",
                email=email,
            )
        session = new_session(user.id, user.locale or request.state.lang)
        response = RedirectResponse(next or "/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            dump_session(session),
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
        )
        return response

    @app.get("/auth/register", response_class=HTMLResponse)
    def register_page(request: Request, user: User | None = Depends(current_user), next: str = ""):
        if user is not None:
            return RedirectResponse("/profile", status_code=303)
        return render(request, "auth.html", user, mode="register", next=next)

    @app.post("/auth/register")
    def register_submit(
        request: Request,
        email: str = Form(""),
        password: str = Form(""),
        display_name: str = Form(""),
        csrf: str = Form(""),
        db: Session = Depends(get_db),
    ):
        check_csrf(request, csrf)
        ip = request.client.host if request.client else "unknown"
        if not rate_limit(f"register:{ip}", 5, 3600):
            return render(request, "auth.html", None, status_code=429, mode="register", error="errors.429_title")
        email = clean_text(email, 320).lower()
        display_name = clean_text(display_name, 120)
        if "@" not in email or "." not in email.split("@")[-1]:
            return render(request, "auth.html", None, status_code=400, mode="register", error="auth.invalid", email=email)
        if len(password) < 8:
            return render(
                request, "auth.html", None, status_code=400, mode="register",
                error="auth.password_short", email=email, display_name=display_name,
            )
        if db.scalar(select(User.id).where(User.email == email)):
            return render(
                request, "auth.html", None, status_code=409, mode="register",
                error="auth.email_taken", email=email, display_name=display_name,
            )
        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name or email.split("@")[0],
            locale=request.state.lang,
        )
        db.add(user)
        db.flush()
        db.add(
            UserProfile(
                user_id=user.id,
                full_name=display_name or user.display_name,
                preferred_language=request.state.lang,
            )
        )
        db.commit()
        session = new_session(user.id, request.state.lang)
        response = RedirectResponse("/profile?ok=auth.welcome", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            dump_session(session),
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
        )
        return response

    @app.post("/auth/logout")
    def logout(request: Request, csrf: str = Form("")):
        check_csrf(request, csrf)
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        return response

    # -- profile ------------------------------------------------------------
    @app.get("/profile", response_class=HTMLResponse)
    def profile_page(request: Request, user: User = Depends(require_user)):
        return render(request, "profile.html", user, profile=user.profile)

    @app.post("/profile")
    def profile_save(
        request: Request,
        csrf: str = Form(""),
        full_name: str = Form(""),
        email: str = Form(""),
        phone: str = Form(""),
        address: str = Form(""),
        headline: str = Form(""),
        summary: str = Form(""),
        skills: str = Form(""),
        languages: str = Form(""),
        certifications: str = Form(""),
        nationality: str = Form(""),
        current_location: str = Form(""),
        target_countries: str = Form(""),
        experience_text: str = Form(""),
        education_text: str = Form(""),
        projects_text: str = Form(""),
        requires_sponsorship: str = Form(""),
        preferred_language: str = Form(""),
        db: Session = Depends(get_db),
        user: User = Depends(require_user),
    ):
        check_csrf(request, csrf)
        profile = user.profile or UserProfile(user_id=user.id)
        if profile.id is None:
            db.add(profile)
        profile.full_name = clean_text(full_name, 200) or profile.full_name
        profile.email = clean_text(email, 320)
        profile.phone = clean_text(phone, 60)
        profile.address = clean_text(address, 500)
        profile.headline = clean_text(headline, 300)
        profile.summary = clean_text(summary, 4000)
        profile.skills = _split_list(skills, 60)
        profile.languages = _split_list(languages, 30)
        profile.certifications = _split_list(certifications, 40)
        profile.nationality = clean_text(nationality, 120)
        profile.current_location = clean_text(current_location, 200)
        profile.target_countries = [c.upper()[:2] for c in _split_list(target_countries, 20)]
        profile.experience = _parse_rows(experience_text, ("title", "company", "start", "end", "description"))
        profile.education = _parse_rows(education_text, ("degree", "institution", "year", "details"))
        profile.projects = _parse_rows(projects_text, ("name", "description"))
        profile.requires_sponsorship = requires_sponsorship in {"1", "true", "on", "yes"}
        profile.preferred_language = normalize_lang(preferred_language or request.state.lang)
        user.display_name = clean_text(full_name, 120) or user.display_name
        user.locale = profile.preferred_language
        db.commit()
        return RedirectResponse("/profile?ok=profile.saved", status_code=303)

    @app.post("/profile/cv")
    async def profile_cv_upload(
        request: Request,
        csrf: str = Form(""),
        db: Session = Depends(get_db),
        user: User = Depends(require_user),
    ):
        check_csrf(request, csrf)
        form = await request.form()
        upload = form.get("cv_file")
        if upload is None or not hasattr(upload, "read"):
            return RedirectResponse("/profile?err=profile.parse_error", status_code=303)
        raw = await upload.read()
        if len(raw) > settings.max_upload_mb * 1024 * 1024:
            return RedirectResponse("/profile?err=profile.parse_error", status_code=303)
        text = _extract_cv_text(raw, getattr(upload, "filename", "") or "")
        if not text:
            return RedirectResponse("/profile?err=profile.parse_error", status_code=303)
        profile = user.profile or UserProfile(user_id=user.id)
        if profile.id is None:
            db.add(profile)
        profile.summary = (profile.summary or "") + ("\n\n" if profile.summary else "") + text[:2500]
        db.commit()
        return RedirectResponse("/profile?ok=profile.parsed", status_code=303)

    @app.post("/profile/delete")
    def profile_delete(
        request: Request, csrf: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_user)
    ):
        check_csrf(request, csrf)
        db.delete(user)
        db.commit()
        response = RedirectResponse("/?ok=profile.deleted", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        return response

    # -- documents ----------------------------------------------------------
    @app.get("/documents", response_class=HTMLResponse)
    def documents_page(
        request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)
    ):
        docs = list(
            db.scalars(
                select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())
            ).all()
        )
        return render(request, "documents.html", user, documents=docs)

    @app.get("/documents/{public_id}", response_class=HTMLResponse)
    def document_view(
        request: Request,
        public_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_user),
    ):
        doc = db.scalar(
            select(Document).where(Document.public_id == public_id, Document.user_id == user.id)
        )
        if doc is None:
            return render(request, "error.html", user, status_code=404, code=404)
        listing = db.get(Listing, doc.listing_id) if doc.listing_id else None
        return render(request, "document.html", user, document=doc, listing=listing, payload=doc.content_json or {})

    @app.post("/documents/{public_id}/edit")
    def document_edit(
        request: Request,
        public_id: str,
        content_text: str = Form(""),
        csrf: str = Form(""),
        db: Session = Depends(get_db),
        user: User = Depends(require_user),
    ):
        check_csrf(request, csrf)
        doc = db.scalar(
            select(Document).where(Document.public_id == public_id, Document.user_id == user.id)
        )
        if doc is None:
            raise HTTPException(404)
        doc.content_text = content_text[:40_000]
        payload = dict(doc.content_json or {})
        payload["edited"] = True
        doc.content_json = payload
        db.commit()
        return RedirectResponse(f"/documents/{public_id}?ok=common.saved", status_code=303)

    @app.post("/documents/{public_id}/delete")
    def document_delete(
        request: Request,
        public_id: str,
        csrf: str = Form(""),
        db: Session = Depends(get_db),
        user: User = Depends(require_user),
    ):
        check_csrf(request, csrf)
        doc = db.scalar(
            select(Document).where(Document.public_id == public_id, Document.user_id == user.id)
        )
        if doc is not None:
            db.delete(doc)
            db.commit()
        return RedirectResponse("/documents?ok=docs.deleted", status_code=303)

    @app.get("/documents/{public_id}/export.{fmt}")
    def document_export(
        request: Request,
        public_id: str,
        fmt: str,
        db: Session = Depends(get_db),
        user: User = Depends(require_user),
    ):
        doc = db.scalar(
            select(Document).where(Document.public_id == public_id, Document.user_id == user.id)
        )
        if doc is None:
            raise HTTPException(404)
        if fmt == "pdf":
            data = render_pdf(doc)
            media = "application/pdf"
        elif fmt == "docx":
            data = render_docx(doc)
            media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            raise HTTPException(404)
        filename = safe_filename(doc.title, doc.language or "en", fmt)
        return Response(
            data,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/jobs/{public_id}/generate")
    def generate_for_listing(
        request: Request,
        public_id: str,
        csrf: str = Form(""),
        doc_type: str = Form("cv"),
        language: str = Form(""),
        tone: str = Form("professional"),
        length: str = Form("standard"),
        country_style: str = Form("international"),
        instruction: str = Form(""),
        hiring_manager: str = Form(""),
        include_relocation: str = Form("1"),
        ai_ack: str = Form(""),
        db: Session = Depends(get_db),
        user: User = Depends(require_user),
    ):
        check_csrf(request, csrf)
        listing = db.scalar(select(Listing).where(Listing.public_id == public_id))
        if listing is None:
            raise HTTPException(404)
        profile = user.profile
        back = (
            f"/{'volunteer' if listing.listing_type == 'volunteer' else 'jobs'}/{public_id}"
        )
        if profile is None or not (profile.experience or profile.education or profile.skills):
            return RedirectResponse(f"{back}?err=docgen.needs_profile", status_code=303)
        if profile.ai_acknowledged_at is None and ai_ack not in {"1", "on", "true"}:
            return RedirectResponse(f"{back}?err=ai.ack_required", status_code=303)
        if profile.ai_acknowledged_at is None:
            profile.ai_acknowledged_at = datetime.now(timezone.utc)
            db.commit()
        if not rate_limit(f"gen:{user.id}", 12, 3600):
            return RedirectResponse(f"{back}?err=errors.429_title", status_code=303)

        from app.llm.documents import GenerationError, generate_document

        try:
            result = _run_coro(
                generate_document(
                    db=db,
                    user_id=user.id,
                    profile=profile,
                    listing=listing,
                    doc_type=doc_type,
                    language=normalize_lang(language or user.locale or request.state.lang),
                    tone=tone,
                    length=length,
                    country_style=country_style,
                    include_relocation=include_relocation in {"1", "on", "true"},
                    hiring_manager=clean_text(hiring_manager, 120),
                    instruction=clean_text(instruction, 800),
                    identity=_identity(request, user),
                )
            )
        except GenerationError as exc:
            key = {
                "quota": "agent.quota_exhausted",
                "profile": "docgen.needs_profile",
                "disabled": "ai.disabled",
            }.get(exc.reason, "agent.error")
            return RedirectResponse(f"{back}?err={key}", status_code=303)
        except Exception:
            log.exception("Document generation failed")
            return RedirectResponse(f"{back}?err=agent.error", status_code=303)
        db.commit()
        return RedirectResponse(f"/documents/{result.document.public_id}?ok=docgen.saved_to_docs", status_code=303)

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page(
        request: Request, db: Session = Depends(get_db), user: User | None = Depends(current_user)
    ):
        allowed = user is not None and user.email.lower() in settings.admin_email_list
        if settings.admin_email_list and not allowed:
            return render(request, "error.html", user, status_code=403, code=404)
        if not settings.admin_email_list and not settings.gemini_api_key:
            # Local development convenience only when no admin list is configured.
            allowed = True
        if not allowed:
            return render(request, "error.html", user, status_code=403, code=404)
        runs = list(
            db.scalars(select(SourceRun).order_by(SourceRun.started_at.desc()).limit(50)).all()
        )
        totals = {
            "jobs": counter(db, "job")["count"],
            "volunteers": counter(db, "volunteer")["count"],
        }
        quotas = {
            slot: quota.status(slot) for slot in ("fast", "quality")
        } if settings.ai_enabled else {}
        return render(request, "admin.html", user, runs=runs, totals=totals, quotas=quotas)

    # -- assistant ----------------------------------------------------------
    @app.post("/api/agent/session")
    def agent_session(
        request: Request, db: Session = Depends(get_db), user: User | None = Depends(current_user)
    ):
        ip = request.client.host if request.client else "unknown"
        if not rate_limit(f"agent-session:{ip}", 10, 60):
            return JSONResponse({"error": "rate_limited"}, status_code=429)
        if not settings.ai_enabled:
            return JSONResponse({"error": "disabled"}, status_code=503)
        existing = db.scalar(
            select(ChatSession)
            .where(
                ChatSession.user_id == (user.id if user else None),
                ChatSession.visitor_token == (None if user else request.state.session.get("vid")),
            )
            .order_by(ChatSession.id.desc())
        )
        if existing is not None:
            return {"session": existing.public_id}
        session = ChatSession(
            user_id=user.id if user else None,
            visitor_token=None if user else request.state.session.get("vid"),
            locale=request.state.lang,
        )
        db.add(session)
        db.commit()
        return {"session": session.public_id}

    @app.post("/api/agent/stream")
    async def agent_stream(request: Request):
        # The stream opens its own session; the request session is short-lived.
        ip = request.client.host if request.client else "unknown"
        if not rate_limit(f"agent:{ip}", 20, 60):
            return JSONResponse({"error": "rate_limited"}, status_code=429)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid_json"}, status_code=400)

        session_cookie = request.state.session
        if not valid_csrf(session_cookie, body.get("csrf")):
            return JSONResponse({"error": "csrf"}, status_code=400)
        message = clean_text(body.get("message", ""), 4000)
        public_id = clean_text(body.get("session", ""), 40)
        if not message:
            return JSONResponse({"error": "empty"}, status_code=400)
        if not settings.ai_enabled:
            return JSONResponse({"error": "disabled"}, status_code=503)

        uid = session_cookie.get("uid")
        vid = session_cookie.get("vid")
        locale = request.state.lang
        identity = f"u{uid}" if uid else f"v{vid}"

        async def event_stream() -> Iterator[str]:
            from app.db import SessionLocal
            from app.llm.agent import AgentContext, run_agent_turn

            db = SessionLocal()
            try:
                user = db.get(User, int(uid)) if uid and str(uid).isdigit() else None
                chat = db.scalar(select(ChatSession).where(ChatSession.public_id == public_id))
                if chat is None:
                    chat = ChatSession(
                        user_id=user.id if user else None,
                        visitor_token=None if user else vid,
                        locale=locale,
                    )
                    db.add(chat)
                    db.commit()
                # Never let a visitor read or post into someone else's chat.
                owns = (
                    (chat.user_id is not None and user is not None and chat.user_id == user.id)
                    or (chat.user_id is None and not user and chat.visitor_token == vid)
                )
                if not owns:
                    yield _sse("error", {"reason": "forbidden"})
                    return
                ctx = AgentContext(
                    db=db,
                    user=user,
                    identity=identity,
                    locale=locale,
                    profile=user.profile if user else None,
                )
                yield _sse("session", {"session": chat.public_id})
                async for event in run_agent_turn(
                    db=db, chat_session=chat, message=message, ctx=ctx
                ):
                    yield _sse(event["event"], event["data"])
                db.commit()
            except Exception:
                log.exception("Agent stream failed")
                db.rollback()
                yield _sse("error", {"reason": "error"})
            finally:
                db.close()

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots():
        return "User-agent: *\nDisallow: /admin\nDisallow: /api/\nDisallow: /documents\n"


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _saved_ids(db: Session, user: User | None) -> set[str]:
    if user is None:
        return set()
    rows = db.execute(
        select(Listing.public_id).join(SavedListing, SavedListing.listing_id == Listing.id).where(
            SavedListing.user_id == user.id
        )
    ).all()
    return {row[0] for row in rows}


def _split_list(value: str, limit: int) -> list[str]:
    return [clean_text(part, 80) for part in str(value or "").replace("\n", ",").split(",") if clean_text(part, 80)][:limit]


def _parse_rows(value: str, fields: tuple[str, ...]) -> list[dict]:
    rows: list[dict] = []
    for line in str(value or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [clean_text(p, 2000) for p in line.split("|")]
        row = {field: (parts[i] if i < len(parts) else "") for i, field in enumerate(fields)}
        if any(row.values()):
            rows.append(row)
    return rows[:30]


def _extract_cv_text(raw: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        try:
            import io

            import pdfplumber

            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                return "\n".join((page.extract_text() or "") for page in pdf.pages[:8]).strip()
        except Exception:
            return ""
    if name.endswith((".txt", ".md")):
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return raw.decode(encoding)[:20_000].strip()
            except UnicodeDecodeError:
                continue
    return ""


def _run_coro(coro):
    """Run an async generator helper from a sync route thread."""
    import asyncio

    return asyncio.run(coro)


app = create_app()
