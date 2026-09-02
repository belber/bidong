# B站机器人 Phase 1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现后端机器人子系统：关注→私信激活码→小程序绑定；用户在视频评论区 @机器人→自动把该视频存入对应用户收藏夹。

**Architecture:** 单机 worker 低频轮询 B站两个需登录的通知流（`x/msgfeed/follow`、`x/msgfeed/at`）；带 cookie 的 `BiliRobotClient` 负责读写；激活码/binding/游标落 PostgreSQL；@ 命中后复用 `collect` 服务写卡（`source=robot`）。

**Tech Stack:** Python 3.11 · FastAPI · SQLAlchemy 2 · Alembic · httpx · pytest + respx

---

## 明确不做（本期）

- 不解析评论正文里的链接，只取「评论所在的视频」。
- 不解析 `#标签`，收藏标签默认用 B站固有标签（`collect` 已实现）。
- 收藏后不回复（不调 `reply/add`）。
- 未绑定用户直接忽略。
- 不做「专属分组」。

---

## File Structure

创建：

- `server/app/services/bilibili_robot.py` — 带 cookie 的机器人客户端（follow/at 通知、发私信、自检）。
- `server/app/services/activation.py` — 激活码生成 / 幂等发码 / 一次性绑定。
- `server/app/routers/binding.py` — `POST /api/binding`、`GET /api/binding`。
- `server/app/robot/__init__.py`、`server/app/robot/worker.py` — 轮询主循环 + 可测的 `run_once()`。
- `server/app/robot/login.py` — 二维码扫码登录脚本（本地运行取 cookie）。
- `server/alembic/versions/xxxx_add_binding_robot_cursor.py` — 迁移。

修改：

- `server/app/models.py` — 新增 `Binding`、`RobotCursor`。
- `server/app/config.py` + `server/.env.example` — 机器人开关 / UID / cookie / 轮询与控频间隔。
- `server/app/services/collect.py` — 增加 `source` 参数，拆出 `collect_video_by_bvid()`。
- `server/app/main.py` — 注册 binding 路由。
- `server/pyproject.toml` — 可选依赖加 `qrcode[pil]`（登录脚本用）。

测试：

- `server/tests/helpers.py` — 增加机器人接口 mock（follow/at/send_msg/nav）。
- `server/tests/test_robot_client.py`、`test_activation.py`、`test_binding.py`、`test_worker.py`、`test_collect_source.py`。

---

## Task 1: 数据模型 + 迁移

**Files:**
- Modify: `server/app/models.py`
- Create: `server/alembic/versions/xxxx_add_binding_robot_cursor.py`
- Test: `server/tests/test_models.py`（若无则新建）

- [ ] **Step 1: 写失败测试**——`Binding` 允许 `user_id` 为空、`bili_uid` 唯一、`activation_code` 唯一；`RobotCursor.kind` 唯一。
- [ ] **Step 2: 运行确认失败**（表不存在）。
- [ ] **Step 3: 实现模型**

```python
class Binding(Base):
    __tablename__ = "binding"
    __table_args__ = (
        UniqueConstraint("bili_uid", name="uq_binding_bili_uid"),
        UniqueConstraint("activation_code", name="uq_binding_activation_code"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), unique=True, nullable=True)
    bili_uid: Mapped[str] = mapped_column(String(32))
    activation_code: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    bound_at: Mapped[datetime | None] = mapped_column(nullable=True)

class RobotCursor(Base):
    __tablename__ = "robot_cursor"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), unique=True)
    last_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_time: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow_naive, onupdate=utcnow_naive)
```

- [ ] **Step 4: 跑测试通过**。
- [ ] **Step 5: 生成 Alembic 迁移**（`alembic revision --autogenerate`），并补降级函数。
- [ ] **Step 6: Commit** `feat(robot): add binding and robot_cursor tables`。

---

## Task 2: 配置项

**Files:** Modify `server/app/config.py`、`server/.env.example`

- [ ] **Step 1: 写失败测试**——`Settings` 含机器人字段且默认关闭。
- [ ] **Step 2: 实现配置**

```python
robot_enabled: bool = False
robot_uid: str = ""
robot_sessdata: str = ""
robot_bili_jct: str = ""
robot_dedeuserid: str = ""
robot_buvid3: str = ""
robot_buvid4: str = ""
robot_poll_interval_seconds: int = 45
robot_send_interval_seconds: int = 5
```

- [ ] **Step 3: `.env.example` 补对应注释与空值**。
- [ ] **Step 4: 跑测试通过**。Step 5: Commit `feat(robot): add robot settings`。

---

## Task 3: collect 服务支持 source + 按 bvid 收藏

**Files:** Modify `server/app/services/collect.py`；Test `server/tests/test_collect_source.py`

- [ ] **Step 1: 写失败测试**——`collect_video(..., source="robot")` 与 `collect_video_by_bvid(db, user, bvid, source="robot")` 返回卡片 `source=="robot"`；默认仍为 `"local"`。
- [ ] **Step 2: 重构**——把现有逻辑拆成 `_collect(db, user, bvid, source)`，`collect_video` 只负责 `resolve_bvid` 后调用 `_collect`，`collect_video_by_bvid` 直接调用 `_collect`。
- [ ] **Step 3: 跑全量回归**（`test_parse.py` 必须仍绿）。
- [ ] **Step 4: Commit** `feat(robot): collect_video supports source and bvid`。

---

## Task 4: 机器人客户端 + 二维码登录

**Files:** Create `server/app/services/bilibili_robot.py`、`server/app/robot/__init__.py`、`server/app/robot/login.py`；Test `server/tests/test_robot_client.py`

- [ ] **Step 1: 写失败测试**——用 respx mock，验证：
  - `get_follow_notifications()` 解析出 `[{mid, uname, time, id}]`
  - `get_at_notifications()` 解析出 `[{mid, uname, bvid, id, time}]`
  - `send_msg(receiver_uid, content)` 携带 `csrf=bili_jct` 与 cookie
- [ ] **Step 2: 实现 `BiliRobotClient`**（所有 endpoint 常量集中在模块顶部，便于实测后改）：

```python
class BiliRobotClient:
    def __init__(self, cookie: dict) -> None: ...
    def get_follow_notifications(self) -> list[dict]: ...   # x/msgfeed/follow
    def get_at_notifications(self) -> list[dict]: ...       # x/msgfeed/at
    def send_msg(self, receiver_uid: str, content: str) -> None: ...  # web_im/send_msg
    def get_self_info(self) -> dict: ...                    # x/web-interface/nav
```

- [ ] **Step 3: 实现 `login.py`**——`qrcode/generate` 拿 `qrcode_key`，用 `qrcode` 库在终端打印二维码，轮询 `qrcode/poll`，成功后把 `SESSDATA/bili_jct/DedeUserID/buvid3/buvid4` 写进 `.env`（已有则覆盖对应行）。
- [ ] **Step 4: 跑测试通过**。Step 5: `pyproject.toml` 可选依赖加 `qrcode[pil]`。Step 6: Commit `feat(robot): add robot client and qr login`。

---

## Task 5: 激活码服务

**Files:** Create `server/app/services/activation.py`；Test `server/tests/test_activation.py`

- [ ] **Step 1: 写失败测试**——`generate_code()` 唯一且长度固定；`issue_activation(db, uid)` 幂等（同一 uid 返回同一个 code）；`bind(db, user_id, code)` 成功后 `bound_at` 非空、二次绑定报错、错误 code 报错。
- [ ] **Step 2: 实现**

```python
def generate_code() -> str: ...                 # secrets，10 位大写字母数字
def issue_activation(db, bili_uid) -> Binding:  # 已存在（未绑定）则返回原记录
def bind(db, user_id, code) -> Binding:         # 未找到/已绑定 → AppError(400/404)
```

- [ ] **Step 3: 跑测试通过**。Step 4: Commit `feat(robot): activation code issue and bind`。

---

## Task 6: binding 路由

**Files:** Create `server/app/routers/binding.py`；Modify `server/app/main.py`；Test `server/tests/test_binding.py`

- [ ] **Step 1: 写失败测试**——`POST /api/binding` 用有效码返回 200 并绑定当前用户；无效码 400；已用码 400；`GET /api/binding` 返回绑定状态（未绑定返回 404 或空）。
- [ ] **Step 2: 实现 `POST /api/binding`（`{code}`）与 `GET /api/binding`**，走 `get_current_user` + `bind()`。
- [ ] **Step 3: 在 `main.py` 注册路由**。Step 4: 跑测试通过。Step 5: Commit `feat(robot): binding endpoints`。

---

## Task 7: worker 单轮逻辑

**Files:** Create `server/app/robot/worker.py`；Test `server/tests/test_worker.py`

- [ ] **Step 1: 写失败测试**——用内存库 + fake client，验证 `run_once()`：
  - 新粉丝 → 生成/重发激活码 + 调 `send_msg` + 更新 follow 游标
  - 同一粉丝重复跑 → 不重复发（幂等）
  - @ 通知且 sender 已绑定 → 收藏对应视频（`source=robot`）
  - @ 通知但 sender 未绑定 → 忽略、不落卡
  - 消息去重（游标推进后不重复处理）
- [ ] **Step 2: 实现 `run_once(db, client)` + `process_follow` / `process_at` + 游标读写**。
- [ ] **Step 3: 跑测试通过**。Step 4: Commit `feat(robot): worker run_once`。

---

## Task 8: 主循环 + 接线

**Files:** Modify `server/app/robot/worker.py`

- [ ] **Step 1: 实现 `main()`**——`robot_enabled` 为假则直接退出；循环内 `run_once` → `sleep(robot_poll_interval_seconds)`；发送控频用 `robot_send_interval_seconds`。
- [ ] **Step 2: 补一条 smoke 测试**（`main` 的可注入 sleep，或只测循环编排函数）。
- [ ] **Step 3: 手写 `README`/命令说明**——`python -m app.robot.worker`、`python -m app.robot.login`。
- [ ] **Step 4: Commit** `feat(robot): worker main loop and cli entrypoints`。

---

## 完成后的上线前实测（需真账号 + cookie + 有网）

1. 跑 `python -m app.robot.login` 扫码拿 cookie 写 `.env`。
2. 实测 `x/msgfeed/follow`、`x/msgfeed/at` 的真实字段，必要时只改 `bilibili_robot.py` 顶部的 endpoint/字段映射。
3. 用小号低频试点，确认无误后再放量；`robot_enabled=false` 可随时整体下线，不影响核心闭环。
