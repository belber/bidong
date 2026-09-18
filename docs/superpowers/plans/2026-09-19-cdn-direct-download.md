# B站 CDN Direct Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move watermarked video and audio downloads to WeChat front-end direct CDN downloads while adding observability, domain governance, and manual-save fallback.

**Architecture:** The FastAPI backend resolves Bilibili `playurl`, returns ordered CDN candidates, records domain sightings, and accepts download events. The mini program downloads candidates with `wx.downloadFile`, saves or shares the file, reports outcomes, and shows a unified fallback tutorial. The admin app adds download monitoring and B站 CDN domain management views.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, WeChat Mini Program native JS, Jest, pytest.

---

### Task 1: Backend schemas and models

**Files:**
- Modify: `server/app/models.py`
- Modify: `server/app/schemas.py`
- Create: `server/alembic/versions/20260919_add_download_event_and_cdn_domain.py`
- Test: `server/tests/test_download_events.py`

- [x] Write failing model/API tests for candidate response, domain recording, event reporting, and admin domain listing.
- [x] Implement `DownloadEvent` and `BiliCdnDomain`.
- [x] Add response schemas and Alembic migration.
- [x] Run targeted pytest.

### Task 2: Direct URL and event services

**Files:**
- Modify: `server/app/routers/media.py`
- Create: `server/app/services/media_download.py`
- Test: `server/tests/test_download_events.py`

- [x] Return `{kind, qn, expires_at, candidates}` with primary and backup URLs.
- [x] Use `platform=html5` only for watermarked MP4; audio uses normal DASH.
- [x] Record unique hosts and configured status.
- [x] Add authenticated event reporting and update domain counters.

### Task 3: Admin APIs

**Files:**
- Modify: `server/app/admin.py`
- Test: `server/tests/test_download_events.py`

- [x] Add download summary/detail endpoints.
- [x] Add domain list/update endpoints.
- [x] Include stale-domain warnings using 30/60 day thresholds.

### Task 4: Mini program direct download

**Files:**
- Create: `miniprogram/utils/mediaDownload.js`
- Test: `tests/mediaDownload.test.js`
- Modify: `miniprogram/utils/api.js`
- Modify: `miniprogram/pages/result/result.js`
- Modify: `miniprogram/pages/result/result.wxml`
- Modify: `miniprogram/pages/result/result.wxss`

- [x] Test candidate iteration, error classification, retry behavior, and fallback state.
- [x] Remove audio pre-download.
- [x] Download video/audio from CDN candidates.
- [x] Report resolve/download/save/share outcomes.
- [x] Add copy-link and unified manual-save tutorial modal.

### Task 5: Admin UI

**Files:**
- Modify: `server/app/admin_static/index.html`

- [x] Add 下载监控 view.
- [x] Add B站域名管理 view.
- [x] Show configured, unconfigured, high-failure, and stale domains.

### Task 6: Verification

- [x] Run `pytest`.
- [x] Run `jest`.
- [x] Review git diff and avoid unrelated workspace changes.
