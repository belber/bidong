# 「B站视频收藏助手」设计文档（Spec）

> 状态：待审阅 ｜ 日期：2026-08-30 ｜ 代号：bili-collector（正式命名待定）

---

## 0. 一句话定位

一个**工具类**微信小程序：把 B站视频存成「卡片」（标题 / 封面 / UP主 / 分区），用**标签**归类，按**收藏月份**分组，点击跳回 B站查看。**只存元数据 + 缩略图，不在服务端存储视频/音频本体；视频/音频下载作为可开关的增值能力，走中转流式、按需取链。**

**特色：** B站机器人账号触发收藏（用户 @机器人 + 链接 + #标签，自动存到自己的收藏夹）。

---

## 1. 范围

### 1.1 Phase 0 —— 核心闭环（先做）

| 功能 | 说明 |
|:--|:--|
| 贴链接解析 | 粘贴 B站链接 → 解析标题/封面/UP主/分区 |
| 存卡片 | 保存为卡片，转存缩略图 |
| 标签 | 给卡片打标签（多对多），分组 = 一种标签 |
| 月份分组 | 按收藏月份分组展示 |
| 跳回 B站 | 点击卡片跳转原视频 |
| 微信登录 | openid 登录，数据按用户隔离 |
| 解析结果页 | 字段化展示解析产物，单字段复制/下载 + 一键导出文本 |
| 媒体下载 | 有水印视频 / 无水印视频 / 纯音频，三档独立开关、中转流式 |

**增值（读向、可选、风险低）：** 弹幕读取（本期做）；评论读取（延后）。

### 1.2 Phase 1 —— B站机器人触发（接着做，已纳入）

| 功能 | 说明 |
|:--|:--|
| 机器人账号 | B站机器人账号，模拟登录 |
| 激活码 + 绑定 | 用户关注机器人 → 机器人私信激活码 → 小程序粘贴激活码绑定 |
| @ 触发收藏 | 用户在视频评论区 @机器人 → 自动把「该评论所在的视频」存到对应用户收藏夹 |

### 1.3 明确不做（本期及近期）

- ❌ 多平台（抖音/小红书/X/油管）—— 未来
- ❌ 一键发布 —— 未来（复用 hermes 基建，先想清版权）
- ❌ 音视频合流、评论正文读取、TV 端无水印片源、管理后台 —— 延后
- ❌ 打赏 / 订阅（个人主体无虚拟支付）
- ❌ 视频搜索（未来）

---

## 2. 架构

```
微信原生小程序 ──HTTPS──▶ 后端 FastAPI ──▶ B站公开 API（view?bvid 等，无登录）
                              │
                    PostgreSQL（user / video_card / tag / binding）
                    对象存储（腾讯云 COS，存转存后的缩略图）

Phase 1 追加：
B站机器人账号(cookie) ──▶ 监听 worker ──▶ 解析 @指令 ──▶ 复用核心闭环存卡片

部署：腾讯云轻量服务器 + 域名 + ICP 备案
```

**核心原则：后端是纯 REST API，与前端无关。** 未来 APP/PC Web 只重写前端，后端复用。

**为什么必须有后端：**
1. 小程序 `request` 要配合法域名，B站接口反爬需要固定 IP + UA，放后端最稳；
2. B站封面 `pic` 是 `http://` 且会防盗链，必须下载转存，不能直接外链。

---

## 3. 技术选型

| 层 | 选型 | 理由 |
|:--|:--|:--|
| 前端 | 微信原生小程序 | 最快最稳、审核顺 |
| 后端 | Python FastAPI | 已锁定；hermes 基建是 Python 系，未来下载能力可复用 |
| 数据库 | PostgreSQL | 稳定、够用 |
| 对象存储 | 腾讯云 COS | 和腾讯云服务器同生态，缩略图成本可忽略 |
| 部署 | 腾讯云轻量服务器 + 域名 | 用户已定 |

---

## 4. 数据模型

```sql
user (
  id          PK,
  openid      unique,        -- 微信 openid
  nickname    text,
  created_at  timestamp
)

video_card (
  id            PK,
  user_id       FK -> user,
  bvid          text,        -- B站视频ID（唯一业务键）
  title         text,
  cover_url     text,        -- 转存到自己 COS 后的 URL
  up_name       text,        -- UP主昵称
  partition     text,        -- B站自带分区（view?bvid 的 tname）
  desc          text,        -- 简介（截断）
  source_url    text,        -- 原始 B站链接（跳转用）
  duration      int,         -- 时长（秒），用于卡片角标
  pubdate       int,         -- B站发布时间（unix 秒）
  source        text,        -- 收藏来源：local（本机）| robot（@壁咚）
  collected_at  timestamp,   -- 收藏时间
  month         text         -- 冗余 'YYYY-MM'，分组索引
)

tag (
  id        PK,
  user_id   FK -> user,
  name      text            -- 标签名；「分组」就是一种标签
)

card_tag (                     -- 卡片-标签 多对多
  card_id   FK -> video_card,
  tag_id    FK -> tag
)

binding (                      -- Phase 1：激活码绑定 B站账号
  id                PK,
  user_id           FK -> user,   -- 发码时为空，绑定后填；一个用户一条
  bili_uid          text unique,  -- 用户的 B站 UID（发码时由机器人记录，用户无需手填）
  activation_code   text unique,  -- 一次性激活码（用户在小程序粘贴，后端反查 UID）
  created_at        timestamp,    -- 发码时间
  bound_at          timestamp     -- 绑定时间，空=未绑定
)

robot_cursor (                  -- Phase 1：worker 轮询游标，重启不重复处理
  id          PK,
  kind        text unique,  -- 'follow_since'（上线基线）| 'at'（评论区@）
  last_id     text,         -- 已处理的最大通知/消息 id
  last_time   int,          -- 已处理的最大时间戳（unix 秒）
  updated_at  timestamp
)
```

- **标签体系**：用户标签多对多；「分组」不单独建模，就是一个标签（如"帅哥"）。机器人触发时 `#标签` 直接落到 card_tag。
- **固有标签落库**：解析时，B站视频自带的标签（`x/tag/archive/tags`，匿名可读）自动作为**默认标签**写入 `card_tag` 预填，成为该卡片的一个默认分组；用户可在收藏夹/卡片上再增删。与用户手动标签共用一套 `tag/card_tag`，不单独建表。
- **月份分组**：由 `collected_at` 派生，`month` 冗余存储便于查询，**与标签正交**。
- **B站分区**（tname）是视频元数据，存 `partition`，与用户自定义标签分开。`view` 接口近期可能不再返回 `tname`/`tname_v2`，后端用 `tid_v2` 反查主分区（频道）名兜底（见 `services/partition.py`）。
- **幂等**：`video_card` 以 `(user_id, bvid)` 建唯一约束，同一用户重复解析同一视频不重复建卡。
- **来源**：`source` 只有 `local` / `robot` 两个值，对应前端「本机 / @壁咚」来源筛选；Phase 0 全部为 `local`。
- **B站 ID 决策**：库表用 `bvid` 作为 `(user_id, bvid)` 唯一键，不存 `aid`。B站小程序跳转直接用 `bvid`；若未来某接口要求数字 ID，按 BV→AV 算法在本地换算，不额外请求 B站接口。
- **媒体下载**：统计数（点赞/评论/收藏/投币）与弹幕条数来自 `view` 接口，不落库、解析时现取；视频/音频下载走中转流式、不落库本体，由三个后台开关控制。

---

## 5. 核心流程

```
Phase 0：贴链接
1. 用户粘贴 B站链接 → POST /api/parse
2. 后端提取 bvid → view?bvid= 拿 title/cover/up/partition
3. 下载 cover → 转存 COS
4. 存库（解析即自动收藏，固有标签落为默认标签）→ 返回卡片；重复解析同一视频幂等返回原卡片
5. 前端按 month 分组，收藏夹内用「关键字搜索 + 分区筛选 + 来源筛选」渲染

Phase 1：机器人触发
1. 用户关注机器人 → worker 检测到新粉丝 → 机器人私信回激活码
2. 用户在小程序粘贴激活码，完成绑定
3. 用户在视频评论区 @机器人
4. worker 轮询 @ 通知 → 解析出「发送者 UID + 评论所在视频」
5. 匹配 binding → 复用核心闭环存卡片（source=robot，标签默认用 B站固有标签）
```

---

## 6. 后端接口（REST）

| 方法 | 路径 | 说明 |
|:--|:--|:--|
| POST | `/api/login` | `{code}` → 换 openid 建用户，返回 JWT token |
| POST | `/api/parse` | `{url}` → 解析并自动收藏，返回卡片（幂等） |
| GET  | `/api/cards?month=YYYY-MM&tag=xxx&source=local\|robot` | 按月份 / 标签 / 来源查卡片 |
| GET  | `/api/cards/:id` | 单卡片 |
| DELETE | `/api/cards/:id` | 删除卡片 |
| POST | `/api/tags` | 新建标签 |
| GET  | `/api/tags` | 用户标签列表（前端筛选用） |
| POST | `/api/cards/:id/tags` | 给卡片打标签 |
| GET  | `/api/cards/:id/media-options?kind=watermarked\|clean\|audio` | 可选清晰度列表 |
| GET  | `/api/cards/:id/download?kind=...&qn=...` | 中转流式下载视频/音频 |
| GET  | `/api/cards/:id/danmaku` | 弹幕 XML |
| GET  | `/api/cards/:id/export?kind=txt\|srt` | 导出文本（txt 全量 / srt 字幕） |

> Phase 0 不提供 `POST /api/cards`；解析即收藏。Phase 1 机器人由 worker 直接写库，也不走该接口。
> Phase 1 提供 `POST /api/binding`（粘贴激活码绑定）与 `GET /api/binding`（查绑定状态）。

> **收藏夹前端交互**：卡片数据量小，筛选/搜索先在前端本地完成。顶部依次为「搜索框（标题 / UP主 / 分区 / 标签关键字）」「来源分段（全部 / 本机 / @壁咚）」「分区 chips（全部 + 去重后的 B站分区）」。标签不再作为一级筛选维度（标签数量不可控、横向 chip 过长），仅保留为卡片元数据并可被搜索命中。

### 6.1 跳转 B站小程序

- B站官方小程序 AppID：`wx7564fd5313d24844`。
- 视频页路径：`pages/video/video?bvid={bvid}`（B站小程序支持直接接收 `bvid`，不需要先转成 `avid`）。
- 小程序需在 `app.json` 配置 `navigateToMiniProgramAppIdList: ["wx7564fd5313d24844"]`。
- 前端使用 `wx.navigateToMiniProgram({ appId, path })` 拉起 B站小程序；本地开发若未配 AppID，则提示用户复制链接。

---

## 7. 机器人子系统要点（Phase 1）

- **两条监听链路**：worker 低频（30–60s）轮询两个需 cookie 的通知流——新粉丝 `x/msgfeed/follow`（发激活码）与评论区 @ `x/msgfeed/at`（触发收藏）
- **激活码走私信**：**只对上线后的新增关注发码**——worker 首次运行记录一个时间基线，之后只处理 `mtime` 晚于基线的粉丝（跳过存量粉丝）；命中后未发过则生成激活码、存 `binding`（记录「激活码 → bili_uid」）→ `web_im/send_msg` 私信回码；已发过则**重发同一个码**（`bili_uid` 唯一，防「取关→再关注」刷码）；已绑定不再发
- **收藏走评论区 @**：用户在视频评论区 @机器人；worker 解析出「发送者 mid + 评论所在视频」，**不解析评论正文里的链接、也不解析 #标签**（本期不做）
- **绑定匹配**：发送者 mid → 查 `binding` → 落到对应 user 的收藏；未绑定直接忽略
- **默认不回复**：收藏成功后不在评论区/私信回「已收藏」，避免触发风控
- **关注检测**：轮询 `x/msgfeed/follow`（新粉丝通知流，需 cookie）取 `user.mid` / `user.uname`；兜底用 `x/relation/followers` 粉丝列表做差集
- **@ 检测**：轮询 `x/msgfeed/at`（@ 通知流，需 cookie），需拿到「发送者 mid / 评论正文 / 评论所在视频 aid/bvid」；字段以实测为准
- **激活码回送**：私信接口 `web_im/send_msg`（`msg[content]` = 激活码）
- **Cookie 前置**：机器人账号须持登录态 `SESSDATA`、`bili_jct`、`DedeUserID`、`buvid3/4`（二维码登录获取，见 bilibili-api.md §5.1）
- **幂等 & 控频（防刷码）**：同一 `bili_uid` 只对应一个激活码（`binding.bili_uid` 唯一）；重发是同一个码；发送控频（每账号间隔数秒）；激活码一次性、绑定后即失效

**风险（已确认，设计时用防御性措施兜底）：**
- 依赖 B站非公开私信/@ 接口 + cookie，有风控/封号/接口变更风险（hermes 投稿血泪史同源）
- **评论区 @ 比私信风险更高**，`x/msgfeed/at` 返回字段未纳入现有调研文档，上线前需实测；接口地址集中配置，实测后只改配置不改逻辑
- 用**一次性小号**、**低频**、**单账号小规模**试点
- 设计成**可随时下线**，不影响核心闭环

---

## 8. 里程碑（实施顺序）

**Phase 0（核心闭环）**
1. 后端地基：FastAPI 骨架 + 解析接口 + 存库 + 缩略图转存（curl 验证）
2. 前端骨架：贴链接 → 解析 → 卡片展示
3. 前端完成：月份分组 + 标签 + 微信登录
4. 部署：腾讯云 + COS + 域名 + 备案
5. 提审发布

**Phase 1（机器人触发）**
6. 机器人账号 + 私信监听 worker
7. 激活码 + 绑定体系
8. @ 指令解析 + 自动收藏
9. 上线（小规模试点）

---

## 9. 风险 & 待办

| 项 | 说明 |
|:--|:--|
| **ICP 备案** | 提前启动（1~2周，个人可办），和写代码并行 |
| 腾讯云服务器购买 | 轻量服务器即可 |
| 机器人风控 | 小号 + 低频 + 可下线（见 §7） |
| 命名待定 | 代号 bili-collector |
| 冷启动流量 | 广告需 500 访客后开，前期无收入 |
