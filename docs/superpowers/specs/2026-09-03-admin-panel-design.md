# 「bili-collector」后台管理端设计（Spec）

> 状态：待实现 ｜ 日期：2026-09-03 ｜ 代号：admin-panel

## 0. 一句话定位

在现有 FastAPI 后端上，**单独暴露一个端口**，提供一个**有密码登录**的 PC Web 后台，用于监控机器人运营数据、维护 B站 Cookie、切换解析能力与配置定时任务。

**前提**：现有库仅存 `user / video_card / tag / binding / robot_cursor`，无法支撑「粉丝数、@评论数、发码成功/失败、解析成功/失败」等统计。故后台需要**新增几张跟踪表 + 一张动态配置表**，并让 worker/解析主链路在运行时写日志、读动态配置。

---

## 1. 部署与形态

| 项 | 决策 |
|:--|:--|
| 前端形态 | 静态单页（原生 JS + ECharts），由 FastAPI 静态目录托管，无独立构建工程（方案 A） |
| 端口 | 管理端独立端口，默认 `8081`（环境变量 `ADMIN_PORT`），API 保持 `8000` |
| 进程 | 新增 `app.admin_app:app`，与 `app.main:app`、`app.robot.worker` 三个进程并行（`dev.sh` 一并启动） |
| 鉴权 | `POST /api/admin/login` 用 `ADMIN_PASSWORD`（env，常量时间比较）换管理 JWT；所有 `/api/admin/*` 需带 `Authorization: Bearer`，管理 JWT 带 `scope="admin"` 标记 |
| 时间 | 全部用上海时区（沿用 `time.py`），「今日」= 上海时区当天 |
| 趋势图 | 支持 7 / 30 / 90 天切换，默认为 30 |

> 管理端 API 与业务 API 分属不同 app，业务端 `main.py` 不受影响，符合「后端纯 REST、前端可重写」。

---

## 2. 页面信息架构

```
后台管理 （/admin，登录后进入）
├── 概览          统计卡 + 近30天趋势 + Cookie 告警条
├── 粉丝监控      累计/今日/趋势 + 明细表
├── 评论@监控     累计/今日/趋势 + 明细表
├── 激活码        发码成功/失败/绑定统计 + 明细 + 批量发码/重发失败
├── 解析统计      @触发 / 贴链接 两个 tab：总数/成功/失败原因 + 明细
├── 账号/Cookie   机器人账号、Cookie 有效性、更新、失效告警、告警邮箱
├── 功能开关      有水印/无水印/纯音频
└── 定时任务      评论轮询 / 关注轮询 / 发码间隔 / 关注发码窗口
```

每个列表页支持：搜索、日期范围切换（7/30/90）、导出 CSV。

---

## 3. 数据模型新增

### 3.1 跟踪表（写入方：worker / 解析主链路）

```sql
follow_event (                   -- 每次「发现新关注」落一条，按 (bili_uid, mtime) 去重
  id            PK
  bili_uid      text, index
  bili_name     text default ''
  mtime         int,             -- B站关注时间(unix)
  sent_code     bool default 0   -- 是否已发送激活码
  bound         bool default 0   -- 是否已绑定
  created_at    datetime         -- 检测到的时间（上海时区当日统计依据）
  UNIQUE(bili_uid, mtime)
)

at_event (                      -- 评论区 @ 通知，按 feed id 去重
  id            PK
  feed_id       text unique      -- 通知唯一 ID
  bili_uid      text, index
  bili_name     text default ''
  bvid          text
  comment       text default ''
  result        text             -- collected | unbound | parse_failed | error
  reason        text default ''
  created_at    datetime
)

activation_log (                -- 每次「发码尝试」落一条
  id            PK
  bili_uid      text, index
  bili_name     text default ''
  code          text
  sent_ok       bool default 0
  send_reason   text default ''  -- 失败原因：risk_control / network / not_found / other
  bound         bool default 0   -- 是否绑定（由 binding 反填）
  created_at    datetime
)

parse_log (                     -- 每次「解析尝试」落一条
  id            PK
  source        text            -- local | robot
  user_id       int null        -- local 时的小程序用户
  bili_uid      text null       -- robot 时的用户 B站 UID
  input         text            -- 输入（url 或 bvid）
  bvid          text null
  ok            bool default 0
  reason        text default '' -- 细分原因（见 §3.3）
  duration_ms   int default 0
  created_at    datetime
)
```

### 3.2 动态配置表

```sql
admin_config (
  id          PK
  key         text unique       -- 配置键
  value       text              -- 文本/JSON 值
  updated_at  datetime
)
```

键清单（读时优先 DB，缺省回退 `settings` 的环境值）：

| key | 默认（env） | 说明 |
|:--|:--|:--|
| `enable_watermarked_video` | `ENABLE_WATERMARKED_VIDEO` | 有水印视频开关 |
| `enable_clean_video` | `ENABLE_CLEAN_VIDEO` | 无水印视频开关 |
| `enable_audio` | `ENABLE_AUDIO` | 纯音频开关 |
| `at_poll_interval` | 30 | @评论 轮询间隔（秒） |
| `follow_poll_interval` | 90 | 关注 轮询间隔（秒） |
| `send_interval` | `ROBOT_SEND_INTERVAL_SECONDS` | 私信发送间隔（秒） |
| `follow_window` | `ROBOT_FOLLOW_WINDOW_SECONDS` | 关注发码窗口（秒） |
| `robot_cookie` | `ROBOT_*` env | JSON：`{SESSDATA,bili_jct,DedeUserID,buvid3,buvid4,robot_uid}` |
| `cookie_valid` | true | Cookie 是否有效 |
| `cookie_last_checked` | — | 最近检查时间 |
| `cookie_last_error` | — | 最近检查错误/失效提示 |
| `alert_enabled` | false | 失效是否发邮件 |
| `alert_email` | — | 告警收件箱 |
| `smtp_host` `smtp_port` `smtp_user` `smtp_pass` | — | SMTP 配置 |

`get_config(key)` / `set_config(key, value)` 封装在 `services/config_store.py`；worker 的 `build_client()` 改为每次从配置服务读 Cookie（env 兜底），使管理端更新 Cookie/schedule 后**不重启即生效**。

### 3.3 解析失败原因细分

| reason | 含义 |
|:--|:--|
| `invalid_url` | 无法解析出 bvid |
| `network_timeout` | 请求 B站超时/网络异常 |
| `api_error` | B站接口返回非 0 / 非 200 |
| `video_unavailable` | 视频不可用/已删除 |
| `cover_fail` | 封面下载失败 |
| `storage_fail` | 封面转存（COS/本地）失败 |
| `partition_missing` | 分区映射缺失 |
| `db_error` | 落库异常 |
| `other` | 其他 |

---

## 4. 管理端 API

统一前缀 `/api/admin`（`app/admin.py` router），除 `login` 外均需管理 JWT。

| 方法 | 路径 | 说明 |
|:--|:--|:--|
| POST | `/login` | `{password}` → `{token}` |
| GET | `/stats/overview` | 统计卡 + 近 N 天趋势 + Cookie 告警（`?days=`） |
| GET | `/stats/followers` | 粉丝累计/今日/趋势（`?days=`） |
| GET | `/stats/followers/detail` | 粉丝明细（`?q=&days=&page=&size=`） |
| GET | `/stats/at` | @评论 累计/今日/趋势 |
| GET | `/stats/at/detail` | @明细（`?q=&days=&page=&size=`） |
| GET | `/stats/activation` | 发码成功/失败/绑定 统计 + 明细 |
| GET | `/stats/parse` | `?source=local\|robot` 总数/成功/失败 + 失败原因分布 |
| GET | `/stats/parse/detail` | `?source=&q=&result=&days=&page=&size=` |
| POST | `/activation/send` | `{uids:[]}` 批量发码 |
| POST | `/activation/retry-failed` | 对「发码失败且未绑定」的账号批量重发 |
| GET | `/cookie/status` | 机器人账号 + Cookie 有效性 |
| POST | `/cookie/check` | 立即 probe 校验并写回状态 |
| POST | `/cookie/update` | `{cookie_text 或各字段}` 更新 Cookie 并保存 |
| GET | `/config/features` | 读取三个开关 |
| PUT | `/config/features` | `{watermarked,clean,audio}` |
| GET | `/config/schedule` | 读取轮询/发码/窗口 |
| PUT | `/config/schedule` | 更新 interval 类配置 |
| GET | `/config/alert` | 告警邮箱/SMTP 配置 |
| PUT | `/config/alert` | 更新告警配置 |
| POST | `/config/alert/test` | 发送测试邮件 |

---

## 5. 主链路改造（写入方）

### 5.1 worker（`robot/worker.py`）

- 拆成两个独立间隔的循环：`follow_poll_interval`（关注→发码）与 `at_poll_interval`（@→收藏），各自记录最后运行时间，避免一个阻塞另一个。
- `process_follow`：每个在窗口内的新粉丝写 `follow_event`（按 `(bili_uid,mtime)` 去重）；发码尝试写 `activation_log`（成功/失败原因）。
- `process_at`：每条 @ 通知写 `at_event`（按 `feed_id` 去重）；触发收藏时写 `parse_log`，失败按 §3.3 记 reason。
- `build_client()`：从配置服务读 Cookie（env 兜底），每次轮询重建，使后台更新即生效。

### 5.2 解析主链路（`services/collect.py` / `routers/parse.py`）

- `collect_video`（贴链接）：包一层 try/except，成功/失败写 `parse_log`（`source=local`、`user_id`），错误归类到 §3.3。
- worker 的 `collect_video_by_bvid`（robot）：同步写 `parse_log`（`source=robot`、`bili_uid`）。
- `routers/parse.py` 的 `media` 开关改从 `admin_config` 读取（env 兜底），而非只读 `settings`。

### 5.3 Cookie 检测与告警（`robot/cookie.py` + `services/notify.py`）

- 管理端「立即检测」→ probe 调用 `x/web-interface/nav`，写回 `cookie_valid / cookie_last_checked / cookie_last_error`。
- worker/后台定时（复用 `at_poll_interval` 或单独 `cookie_check_interval`）检测；一旦由「有效」变「失效」且 `alert_enabled`，调用 `notify.send_alert_email` 发送告警。
- 开发环境 SMTP 缺失时，测试用 monkeypatch/mock，不发真实邮件。

---

## 6. 测试策略（TDD）

后端先写失败测试再实现：
- `test_tracking_logs.py`：follow_event / at_event / activation_log / parse_log 的去重、结果与原因写入。
- `test_worker_dynamic.py`：worker 读动态 interval/cookie；拆环后「一坏不影响另一环」。
- `test_admin_api.py`：鉴权（未登录 401）、各 stats 汇总/趋势/明细、批量发码、重发失败、配置 CRUD、Cookie check。
- `test_config_store.py`：get/set + env 兜底。
- `test_parse_log.py`：贴链接成功/失败落到 parse_log 且 reason 归类正确。

静态前端不纳入 pytest，运行时手动验证。

---

## 7. 风险与边界

- 管理端暴露公网端口：必须密码登录；建议服务器防火墙仅放行运维 IP，或配合 HTTPS（反代）。
- Cookie 存储仍在 DB：仅限运维内网/受信环境；生产建议至少 `alert_email` 不存密码类敏感信息（或不启用 SMTP 密码持久化，用独立 env）。
- B站接口仍然有风控风险：管理端所有「发码/重发」沿用现有 `send_interval` 控频，不绕过。
- `at` 与 `follow` 拆环后，worker 单循环可能重叠调用 B站接口；用「最小间隔 + 上一轮结束时间」避免过频。
