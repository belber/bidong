# 「视频出处（原up主）」实现计划

> 设计见 `docs/superpowers/specs/2026-09-25-repost-source-design.md`，主文档见 `docs/spec.md` §11。
> 项目铁律：改代码必须 TDD（先写失败的测试）。每个 Task 的最后一步是跑测试 + 提交。

**目标：** 小程序解析「帅哥录屏」的稿件时，结果页显示「原平台 / 原up主」，数据由家中小主机上报。

**架构：** 小主机 → `POST /api/sources/ingest`（token 鉴权、按 bvid 幂等）→ `video_source` 表；
`POST /api/parse` 读该表，用 UP主 mid 白名单决定是否返回 `origin`。

**技术栈：** FastAPI + SQLAlchemy + Alembic + PostgreSQL/SQLite；微信原生小程序；pytest + jest。

---

## 文件结构

| 文件 | 职责 |
|:--|:--|
| `server/app/models.py` | 新增 `VideoSource` 表；`VideoCard` 增 `up_mid` 列 |
| `server/app/schemas.py` | `OriginOut`；`ParseResult.origin`；上报请求/响应模型 |
| `server/app/services/repost_source.py` | 平台名映射、bvid 校验、upsert、读出处、白名单判断、统计 |
| `server/app/routers/sources.py` | `POST /api/sources/ingest`（token 鉴权） |
| `server/app/routers/parse.py` | 解析结果挂 `origin`（缓存命中时同样重新计算） |
| `server/app/services/collect.py` | 落 `up_mid`；返回值不变 |
| `server/app/services/bilibili.py` | `VideoMeta.up_mid` |
| `server/app/services/config_store.py` | 4 个出处相关配置的读写 |
| `server/app/admin.py` | 管理端出处统计 / CSV 导入 / 配置读写 |
| `server/alembic/versions/20260925_add_repost_source.py` | 建表 + 加列 |
| `miniprogram/pages/result/result.{js,wxml,wxss}` | 结果页专属区块 |
| `docs/视频出处上报接口.md` | 交给 Hermes 的接口文档（含字段、示例、重试规则） |
| `server/tests/test_sources.py`、`server/tests/test_repost_origin.py`、`tests/result-origin.test.js` | 测试 |

---

### Task 1：数据模型与迁移

**Files:** `server/app/models.py`、`server/alembic/versions/20260925_add_repost_source.py`

- [x] 在 `models.py` 末尾新增 `VideoSource`（字段见设计 §4.2），`VideoCard` 增加 `up_mid`（`String(32)`，默认 `""`）。
- [x] 迁移 `revision = "20260925repost"`，`down_revision` 指向当前 head（`5b6c7d8e9f0a`）：
  `create_table("video_source", ...)`、`create_index ix_video_source_bvid`、`add_column("video_card", "up_mid")`。
- [x] 验证：`cd server && python -m pytest tests/test_migrations.py -q` → PASS。
- [x] 提交：`git commit -m "feat: 新增视频出处表与 video_card.up_mid"`。

### Task 2：出处上报接口

**Files:** `server/app/routers/sources.py`、`server/app/services/repost_source.py`、`server/app/main.py`、`server/tests/test_sources.py`

- [x] **先写测试**（`server/tests/test_sources.py`）：
  - 未配置 token → `503`
  - token 不对 → `401`
  - 正确 token + `{"items":[一条]}` → `200`，`created=1`，库里能查到
  - 同一 bvid 再报一次（改 `author_name`）→ `updated=1`，库里只有 1 行且值更新
  - 空字段不覆盖已有值（先报有作者，再报一条无作者的 → 作者仍在）
  - `bvid` 不合法（`"BV1"`）→ 进 `rejected`，库里没有
  - 单条对象、数组两种形态都能收
  - 超过 500 条 → `400`
- [x] 跑测试确认失败：`cd server && python -m pytest tests/test_sources.py -q`
- [x] 实现 `services/repost_source.py`：`BVID_RE`、`normalize_payload`、`upsert_items(db, items) -> (created, updated, rejected)`、`PLATFORM_LABELS`、`platform_label()`。
- [x] 实现 `routers/sources.py`：读 header `X-Ingest-Token`，`hmac.compare_digest` 比较；在 `main.py` 注册 router。
- [x] 跑测试确认通过。
- [x] 提交：`git commit -m "feat: 新增视频出处上报接口"`。

### Task 3：来源读取与配置项

**Files:** `server/app/services/repost_source.py`、`server/app/services/config_store.py`、`server/app/config.py`、`server/tests/test_repost_origin.py`

- [x] **先写测试**：
  - `up_mid` 命中白名单 + 表里有记录 → `origin` 各字段正确、`platform_label == "抖音"`
  - 命中白名单 + 表里没记录 → `origin` 非空但 `platform_label == ""`（前端显示「整理中」）
  - `up_mid` 不在白名单 → `None`
  - 白名单为空 → `None`
  - 白名单支持逗号分隔多个 mid
- [x] 实现 `is_repost_channel(db, up_mid)`、`get_origin(db, bvid, up_mid)`；`config_store` 增
  `repost_config()` / `set_repost_config()` / `source_ingest_token()` / `set_source_ingest_token()`；
  `config.py` 增 4 个 settings 字段（`repost_up_mid` 默认 `3707052465589015`）。
- [x] 跑测试通过 → 提交 `git commit -m "feat: 视频出处读取与账号白名单配置"`。

### Task 4：解析结果带 origin

**Files:** `server/app/routers/parse.py`、`server/app/services/collect.py`、`server/app/services/bilibili.py`、`server/tests/test_parse.py`

- [x] **先写测试**：解析白名单账号的视频 → 响应 `origin` 非空；解析普通视频 → `origin` 为 `null`；
  缓存命中（同用户二次解析）时 `origin` 仍然正确。
- [x] `bilibili.py` 的 `VideoMeta` 增 `up_mid: str = ""`，从 `owner.mid` 取值。
- [x] `collect.py` 新建/已有卡片都写 `up_mid`。
- [x] `parse.py` 两条返回路径都调用 `repost_source.get_origin(...)` 并塞进 `ParseResult`。
- [x] 跑 `python -m pytest tests/test_parse.py -q` 通过 → 提交 `git commit -m "feat: 解析结果返回视频出处"`。

### Task 5：管理端出处台账

**Files:** `server/app/admin.py`、`server/app/services/repost_source.py`、`server/app/admin_static/index.html`、`server/tests/test_admin_api.py`

- [x] **先写测试**：
  - `GET /api/admin/sources/stats` → `total` / `with_author` / `without_author` / `last_updated_at`
  - `POST /api/admin/sources/import`（body `{"csv": "bvid,platform,...\n..."}`）→ 返回 created/updated/rejected
  - `GET/PUT /api/admin/config/repost` → 读写 `repost_up_mid` / `repost_account_name` / `repost_account_avatar_url` / `source_ingest_token`
- [x] 实现（复用 `upsert_items`）；管理端静态页加「视频出处」页：覆盖率卡片 + 导入框 + 配置表单。
- [x] 跑 `python -m pytest tests/test_admin_api.py -q` 通过 → 提交 `git commit -m "feat: 管理端视频出处台账与导入"`。

### Task 6：结果页专属区块

**Files:** `miniprogram/pages/result/result.js`、`result.wxml`、`result.wxss`、`tests/result-origin.test.js`

- [x] **先写测试**（源码断言，沿用 `tests/` 现有风格）：
  - wxml 里有 `origin` 判断、`帅哥录屏 · 原up主是谁`、`原平台`、`原up主`、`粉丝专属`
  - `复制主页` 绑定 `onCopyAuthorHome`
  - js 里 `onCopyAuthorHome` 使用 `origin.authorUrl` 且 `wx.setClipboardData`
  - wxml 里区块外层 `wx:if="{{origin}}"`（`origin` 为空时不渲染）
  - 有「整理中」和「待补充」两段文案
- [x] 跑 `npx jest tests/result-origin.test.js` 确认失败。
- [x] 实现：`result.js` 取 `res.origin`、新增 `onCopyAuthorHome`；wxml 插入卡片；wxss 加 `.src-card` 等样式。
- [x] 跑 `npx jest` 全绿 → 提交 `git commit -m "feat(miniprogram): 结果页展示原up主专属区块"`。

### Task 7：交付文档

**Files:** `docs/视频出处上报接口.md`

- [x] 写接口文档：鉴权、三种请求体、字段表、示例、响应、错误码、幂等规则、重试建议、curl 自测命令。
- [x] 与用户确认 token，按 `X-Ingest-Token` 交付。
- [x] 提交：`git commit -m "docs: 视频出处上报接口文档"`。

---

## 验收

- `cd server && python -m pytest -q` 全绿（含既有 500+ 用例）
- `npx jest` 全绿
- 真机/开发工具：解析帅哥录屏的视频 → 出现「原up主是谁」；解析其他 UP 主 → 无此区块
