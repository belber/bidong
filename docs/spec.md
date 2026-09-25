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
| 媒体下载 | 有水印视频 / 纯音频返回 B站 CDN 直链，由小程序前端直接下载；无水印视频暂关闭，待支持音视频合流后再开放 |

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
  source        text,        -- 收藏来源：local（本机）| robot（@壁咚咚）
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
  kind        text unique,  -- 'at'（评论区@）
  last_id     text,         -- 已处理的最大通知/消息 id
  last_time   int,          -- 已处理的最大时间戳（unix 秒）
  updated_at  timestamp
)

video_source (                  -- 「帅哥录屏」稿件出处，全局共用，不按用户分
  id                PK,
  bvid              text unique,   -- 唯一键，一条视频一条出处
  title             text,
  platform          text,          -- douyin / x / youtube / ...
  author_name       text,          -- 原作者昵称
  author_id         text,          -- 原作者稳定 ID（昵称会改）
  author_url        text,          -- 原作者主页
  source_url        text,          -- 源视频链接
  source_video_id   text,
  bili_published_at text,          -- YYYY-MM-DD（源站发布时间拿不到）
  note              text,          -- 拿不到时的原因，如 parse失败 404
  created_at        timestamp,
  updated_at        timestamp
)
```

- **标签体系**：用户标签多对多；「分组」不单独建模，就是一个标签（如"帅哥"）。机器人触发时 `#标签` 直接落到 card_tag。
- **固有标签落库**：解析时，B站视频自带的标签（`x/tag/archive/tags`，匿名可读）自动作为**默认标签**写入 `card_tag` 预填，成为该卡片的一个默认分组；用户可在收藏夹/卡片上再增删。与用户手动标签共用一套 `tag/card_tag`，不单独建表。
- **月份分组**：由 `collected_at` 派生，`month` 冗余存储便于查询，**与标签正交**。
- **B站分区**（tname）是视频元数据，存 `partition`，与用户自定义标签分开。`view` 接口近期可能不再返回 `tname`/`tname_v2`，后端用 `tid_v2` 反查主分区（频道）名兜底（见 `services/partition.py`）。
- **幂等**：`video_card` 以 `(user_id, bvid)` 建唯一约束，同一用户重复解析同一视频不重复建卡。
- **来源**：`source` 只有 `local` / `robot` 两个值，对应前端「本机 / @壁咚咚」来源筛选；Phase 0 全部为 `local`。
- **B站 ID 决策**：库表用 `bvid` 作为 `(user_id, bvid)` 唯一键，不存 `aid`。B站小程序跳转直接用 `bvid`；若未来某接口要求数字 ID，按 BV→AV 算法在本地换算，不额外请求 B站接口。
- **媒体下载**：统计数（点赞/评论/收藏/投币）与弹幕条数来自 `view` 接口，不落库、解析时现取；视频/音频下载走中转流式、不落库本体，由三个后台开关控制。
- **视频出处**：`video_source` 只服务「帅哥录屏」这一个账号的溯源需求（见 §11），
  由小主机（Hermes）上报，按 `bvid` 幂等 upsert；表里有没有这条 bvid **不等于**这条视频是不是该账号的，
  判断归属用 UP主 mid 白名单。详见 §11。

---

## 5. 核心流程

```
Phase 0：贴链接
1. 用户粘贴 B站链接 → POST /api/parse
2. 后端提取 bvid → view?bvid= 拿 title/cover/up/partition
3. 下载 cover → 转存 COS
4. 存库（解析即自动收藏，固有标签落为默认标签）→ 返回卡片；重复解析同一视频幂等返回原卡片
5. 后端对同一 `(user, bvid)` 的解析结果做 60 秒内存缓存（`PARSE_CACHE_SECONDS`），重复解析快速返回、减少 B站调用
6. 前端按 month 分组，收藏夹内用「关键字搜索 + 分区筛选 + 来源筛选」渲染

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
| GET  | `/api/config/public` | 小程序公开 UI 配置（`robot_guide` / `share`） |
| DELETE | `/api/cards/:id` | 删除卡片 |
| POST | `/api/tags` | 新建标签 |
| GET  | `/api/tags` | 用户标签列表（前端筛选用） |
| POST | `/api/cards/:id/tags` | 给卡片打标签 |
| GET  | `/api/cards/:id/media-options?kind=watermarked\|clean\|audio` | 可选清晰度列表 |
| GET  | `/api/cards/:id/download?kind=...&qn=...` | 中转流式下载视频/音频 |
| GET  | `/api/cards/:id/danmaku` | 弹幕 XML |
| GET  | `/api/cards/:id/export?kind=txt\|srt` | 导出文本（txt 全量 / srt 字幕） |
| POST | `/api/sources/ingest` | 小主机上报「帅哥录屏」稿件出处，`X-Ingest-Token` 鉴权，按 bvid 幂等 upsert（见 §11） |

> Phase 0 不提供 `POST /api/cards`；解析即收藏。Phase 1 机器人由 worker 直接写库，也不走该接口。
> Phase 1 提供 `POST /api/binding`（粘贴激活码绑定）、`GET /api/binding`（查绑定状态）与 `DELETE /api/binding`（解绑）。

> 公开配置中的 `robot_guide` 同时控制首页引导、我的页引导以及「关于」页的机器人亮点文案展示。

> **收藏夹前端交互**：卡片数据量小，筛选/搜索先在前端本地完成。顶部依次为「搜索框（标题 / UP主 / 分区 / 标签关键字）」「来源分段（全部 / 本机 / @壁咚咚）」「分区 chips（全部 + 去重后的 B站分区）」。标签不再作为一级筛选维度（标签数量不可控、横向 chip 过长），仅保留为卡片元数据并可被搜索命中。

### 6.1 跳转 B站小程序

- B站官方小程序 AppID：`wx7564fd5313d24844`。
- 视频页路径：`pages/video/video?bvid={bvid}`（B站小程序支持直接接收 `bvid`，不需要先转成 `avid`）。
- 小程序需在 `app.json` 配置 `navigateToMiniProgramAppIdList: ["wx7564fd5313d24844"]`。
- 前端使用 `wx.navigateToMiniProgram({ appId, path })` 拉起 B站小程序；本地开发若未配 AppID，则提示用户复制链接。

---

## 7. 机器人子系统要点（Phase 1）

- **两条监听链路**：worker 低频（30s）轮询两个需 cookie 的通知流——新粉丝 `x/relation/followers`（发激活码）与评论区 @ `x/msgfeed/at`（触发收藏）
- **激活码走私信**：**只给最近 30 分钟内（`ROBOT_FOLLOW_WINDOW_SECONDS`，可配置）关注的粉丝发码**——按粉丝列表的 `mtime` 做滑动窗口，旧粉丝一律跳过；命中后未发过则生成激活码、存 `binding`（记录「激活码 → bili_uid」）→ `web_im/send_msg` 私信回码；**取关后重新关注（`mtime` 更新）会重发同一个码**（`bili_uid` 唯一，防「取关→再关注」刷码）；已绑定不再发
- **收藏走评论区 @**：用户在视频评论区 @机器人；worker 解析出「发送者 mid + 评论所在视频」，**不解析评论正文里的链接、也不解析 #标签**（本期不做）
- **绑定匹配**：发送者 mid → 查 `binding` → 落到对应 user 的收藏；未绑定直接忽略
- **默认不回复**：收藏成功后不在评论区/私信回「已收藏」，避免触发风控
- **关注检测**：轮询 `x/relation/followers`（粉丝列表）取 `mid` / `uname` / `mtime`（关注时间）
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


---

## 10. 媒体直连下载与 CDN 域名治理

### 10.1 范围

- 第一期支持 `kind=watermarked`：`fnval=1&platform=html5`，返回完整 MP4，可直接 `wx.downloadFile` 后保存相册。
- 第一期支持 `kind=audio`：DASH 音频轨 `.m4s`，下载后按 `.m4a` 命名并转发；真机需验证播放兼容性。
- `kind=clean` 暂不支持：DASH 视频轨不含音频，需要合流，功能开关保持关闭。
- 后端只负责调用 B站 `playurl`、返回候选直链、记录域名和下载事件，不代理视频/音频流量。

### 10.2 直链响应

`GET /api/cards/:id/download-url?kind=...&qn=...` 返回：

```json
{
  "kind": "watermarked",
  "qn": 16,
  "expires_at": 1789752728,
  "candidates": [
    {
      "url": "https://upos-sz-mirrorcoso1.bilivideo.com/xxx.mp4?...",
      "host": "upos-sz-mirrorcoso1.bilivideo.com",
      "configured": true
    }
  ]
}
```

- 候选顺序：B站主地址，然后 `backup_url`。
- 后端按 host 去重，跳过空值和带非 80/443 端口的动态 PCDN 域名。
- `configured` 来自域名管理表，表示「是否已经登记到微信后台」，供前端决定自动下载策略。
- `download-url` 返回所有合法候选和各自的 `configured` 标记；后端不因「没有已配置域名」返回错误。
- 音频仍由后端中转下载，小程序直接请求 `/api/cards/:id/download?kind=audio`，不经过 `download-url` 候选与手动保存弹窗。
- 前端自动下载只尝试 `configured=true` 的候选；如果没有任何已配置候选，前端直接打开「自动下载失败，手动保存」弹窗，让用户复制链接，不上报为后端错误。
- 前端下载视频时，对多个已配置候选并发下载（`downloadMediaParallel`），任一候选成功即返回，并取消其余任务，减少单个慢速节点或过期链接导致的卡死与超时。
- 实际是否放行仍以微信后台配置为准。
- 签名 URL 不落库；监控只保存 host 与错误摘要，避免敏感查询参数扩散。

### 10.3 前端下载流程

```
用户点击下载视频
→ 请求 download-url
→ 并发尝试所有已配置 candidates（任一成功即取消其余）
→ wx.downloadFile
→ 成功：保存相册
→ 失败：上报事件，识别失败类型并展示兜底
```

音频下载走后端中转：`/api/cards/:id/download?kind=audio` 直接 `wx.downloadFile`，成功后转发文件，失败时按钮显示「重试」。

- 音频文件可能很大（如整场演唱会 Hi-Res），下载成功后直接用 `wx.downloadFile` 返回的临时文件路径分享，不复制到 `wx.env.USER_DATA_PATH`（该本地用户目录有 200MB 总大小上限，复制大音频会报 `the maximum size of the file storage limit is exceeded`）。字幕、弹幕、评论等小文本仍复制到本地用户目录以便「再次保存」。

- 结果页不预下载视频/音频/字幕/弹幕/评论；所有导出项都按需触发，避免进入页面即消耗流量和后端计算。
- 水印视频下载时，前端通过 `DownloadTask.onProgressUpdate` 更新 0-100% 进度，并展示已下载/总大小。
- 无已配置候选时，前端记录 `resolve` 阶段 `domain_not_registered` 事件，并展示手动保存弹窗，不弹普通错误提示。
- 字幕、弹幕、评论、音频下载时，按钮显示百分比，并在对应字段下方展示全宽进度条。
- 字幕、弹幕、评论、音频下载时，进度条下方展示「已下载/总大小 · 实时速度」，速度由 `onProgressUpdate` 两次回调的字节差与时间差计算。
- 字幕、弹幕、评论、音频使用统一的导出状态机：`idle` / `downloading` / `ready` / `failed`。
  - `idle`：按钮显示「下载」；
  - `downloading`：按钮禁点并显示百分比，同一行展示下载进度；
  - `ready`：按钮变成「保存」，并 toast「已下载，请点击保存」；由于 `shareFileMessage` 必须由用户 TAP 手势直接触发，下载完成后不能自动唤起分享；
  - `failed`：按钮显示「重试」，保留失败原因上报；
  - 保存成功后按钮显示「再次保存」，支持重复分享。
- 切换到另一张卡片时清空导出项的本地路径和状态。
- `wx.downloadFile` 失败且错误信息包含 `url not in domain list` 时，判定为微信合法域名未配置。
- 视频无可用候选或下载失败时，弹出「备用保存方式」弹窗，不使用「失败 / 错误 / 异常」等负面词。
- 音频下载失败时按钮显示「重试」，不弹备用保存弹窗。
- 弹窗结构：标题「换一种方式保存」；副标题「当前视频链接暂不支持在小程序内直接保存，复制链接后，用手机浏览器打开即可保存视频」；中间为 iOS / Android 双平台简洁步骤卡片（iPhone：复制链接 → 用 Safari 打开 → 保存到「文件」；Android：复制链接 → 用 Chrome 打开 → 点击下载）；底部提示「链接可能有时效，请及时保存」与「复制链接」主按钮。不使用教程长图，定位为「另一种保存方式」而非错误提示。

### 10.4 下载事件

新增 `download_event`，每次关键阶段成功或失败都上报：

- 字段：`user_id`、`card_id`、`bvid`、`video_title`、`source_url`、`kind`、`qn`、`host`、`candidate_index`、`stage`、`status`、`error_type`、`error_message`、`http_status`、`wx_err_msg`、`created_at`。
- `video_title` / `source_url` 由后端在上报时从**该用户自己的卡片**冗余落库（不采信客户端传值），卡片删除后明细仍可读。
- 「下载视频链接」存的是 **B站原视频链接**，不是 CDN 直链：签名直链数小时内即失效、复现不了，且按 §10.2 的规则不落库，避免敏感查询参数扩散。CDN 侧只保留 `host`。
- 下载监控明细按「用户 openid + 视频名称 + 视频链接」展示：`openid` 由 `user_id` 关联查出，`q` 支持按 bvid / 视频标题 / openid / 域名 / 错误信息搜索。
- `stage`：`resolve` / `download` / `prepare` / `save` / `share`。
- `status`：`success` / `fail`。
- `error_type` 优先分类为 `domain_not_configured`、`domain_not_registered`、`expired`、`http_error`、`permission`、`wx_error`、`unknown`。
- 区分规则：`domain_not_configured` 表示微信 `downloadFile` 真实返回 `url not in domain list`；`domain_not_registered` 表示后端在返回候选前检查数据库，未找到任何 `is_configured=true` 的 CDN 域名。
- 管理端展示成功率、失败原因、失败明细、域名分布和最近趋势。

### 10.5 B站 CDN 域名治理

新增 `bili_cdn_domain`：

- 字段：`host`、`is_configured`、`first_seen_at`、`last_seen_at`、`seen_count`、`download_success_count`、`download_failure_count`、`notes`。
- 后端每次解析 `download-url` 都把候选 host 自动入库并更新 `seen_count`、`last_seen_at`。
- 管理端可手动标记 host 是否已配置到微信 `downloadFile合法域名`。
- 管理端支持批量粘贴微信后台域名串（`https://a;https://b`、每行一个或 Markdown 链接），自动规范化、去重并导入：新域名直接登记为已配置，已在库但未配置的更新为已配置，已配置的跳过；完成后提示新增、更新、跳过和无效项。
- 排序和提醒：
  1. 未配置且已出现；
  2. 下载失败率高；
  3. 已配置但建议删除；
  4. 已配置且正常使用。
- 闲置规则：`30` 天未出现标记「可能闲置」，`60` 天未出现标记「建议删除」。系统只提醒，不自动删除微信后台配置。

### 10.6 微信后台配置

- B站 CDN 直链必须配置在微信小程序后台的 `downloadFile合法域名`，不是 `request合法域名`。
- 自有 API 仍配置在 `request合法域名`。
- 首批建议配置实测主域名：`upos-sz-mirrorcoso1.bilivideo.com`、`upos-sz-estgcos.bilivideo.com`、`upos-sz-mirrorcos.bilivideo.com`、`upos-sz-mirrorcosb.bilivideo.com`、`upos-sz-mirrorhwb.bilivideo.com`、`upos-sz-mirrorhw.bilivideo.com`、`upos-sz-mirrorbd.bilivideo.com`、`upos-sz-mirrorali.bilivideo.com`、`upos-sz-mirroralib.bilivideo.com`、`upos-sz-estgoss.bilivideo.com`、`upos-sz-mirrorzos.bilivideo.com`、`upos-sz-mirror14b.bilivideo.com`。
- 后续以域名管理页「未配置且已出现」为准逐步补充。

### 10.7 运营管理

管理端「运营管理」统一管理通知通道、告警和每日运营报告。通知通道支持邮件与 Server 酱。

告警类型：

1. 机器人 Cookie 失效：仅在「曾经校验有效 → 本次失效」时触发，避免首次配置误报。
2. B站 CDN 未配置域名：`download-url` 登记域名时，若发现 `is_configured=false`，触发告警。

未配置域名告警按 host 去重，同一 host 24 小时内只告警一次；只有任一通道发送成功后才记录告警时间，避免通道未配置时吞掉后续通知。

Server 酱使用 `SendKey`，调用 `POST https://sctapi.ftqq.com/<SendKey>.send`，参数 `title` 和 `desp`。

每日运营报告由 API 进程的后台任务每分钟检查一次，到达配置时间后发送前一天的数据，发送成功后记录 `report_last_sent_date` 防止重复。报告内容：

- 用户：今日新增、累计用户、500 目标进度、今日访问 UV/PV。
- 解析：手动解析、机器人解析的成功/失败次数、新增收藏卡片。
- 下载：下载请求、成功、失败、成功率、视频/音频分布、失败原因 Top、失败域名 Top、失败后复制链接次数；音频 / 评论 / 弹幕按去重用户统计成功与失败。
- 机器人与域名：新增关注、发码成功、绑定成功、未配置域名总数、新出现的未配置域名、Cookie 状态。

访问 UV 由 `visit_event` 统计，小程序首页每天最多上报一次访问；失败后复制链接通过 `download_event(stage=fallback, status=copy_link)` 统计。

### 10.8 访问监控

管理端「访问监控」用来看**有哪些用户访问过小程序**，数据源是 `visit_event`（`user_id`、`path`、`created_at`），由小程序首页每天最多上报一次。

- **汇总**：今日 UV / 上报次数、近 N 天 UV / 上报次数、累计去重用户数。
- **趋势**：按上海时区日期给出每日 UV 与上报次数。
- **口径提醒**：埋点是"每个用户每天最多上报一次"，所以「上报次数」实际等于访问天数，不是点击量；UV 才是真实用户数。管理端文案按此表述，避免误读。
- **明细**：按访问时间倒序，每行展示访问时间（上海时区）、用户 openid、昵称（有则显示）、页面 `path`；`q` 支持按 openid / 昵称 / 页面搜索，支持分页。
- **口径**：UV 为 `visit_event.user_id` 去重数——只有登录用户才会上报，因此 UV 等于"访问过的微信用户数"；「累计去重用户」不受天数区间限制，用于对齐 500 访客目标。
- **已知限制**：`path` 目前恒为 `pages/home/home`（只在首页上报）；若以后要在其他页面补埋点，明细无需改动即可区分。

---

## 11. 视频出处（原up主）

完整设计与取舍见 `docs/superpowers/specs/2026-09-25-repost-source-design.md`。

### 11.1 定位

给 B站账号「帅哥录屏」的粉丝看的溯源信息：解析结果页多出一块「帅哥录屏 · 原up主是谁」，
写明这条视频从哪个平台、搬自谁。**只出现在帅哥录屏自己的稿件上**，其他 UP 主的视频解析结果页不变。

### 11.2 数据来源

小主机（Hermes）自动发布「帅哥录屏」的视频时，顺手把这一条的出处 POST 给后端；
历史 124 条走一次性批量导入。**不解析 Markdown 台账**（脚注、重复编号、缺号、写法不统一，太脆）。

| 字段 | 说明 |
|:--|:--|
| `bvid` | 唯一键 |
| `platform` | `douyin` / `x` / `youtube` / … 只能从源链接域名推断 |
| `author_name` | 原作者昵称（**会改，不能当唯一标识**） |
| `author_handle` | 平台上唯一可搜索的账号标识：抖音号 / X 的 screen_name / YouTube 的 @handle |
| `author_id` / `author_url` | 稳定 ID / 主页 |
| `source_url` / `source_video_id` | 源视频链接与 ID |
| `bili_published_at` | B站发布日；**源站发布时间拿不到** |
| `note` | 拿不到时的原因，如 `parse失败 404` |

**约定**：拿不到就留空 + `note` 写原因，**不猜**；一条视频只报一条「主要出处」= 画面来源，
混源视频（画面来自 X、BGM 来自抖音）只报画面来源。

### 11.3 上报接口

`POST /api/sources/ingest`，请求头 `X-Ingest-Token`。请求体接受
`{"items":[...]}`、单个对象或数组，单次最多 500 条。响应 `{"ok":true,"created":n,"updated":n,"rejected":[...]}`。

- 按 `bvid` 幂等 upsert → **重发永远安全**。
- `bvid` 不匹配 `^BV[0-9A-Za-z]{10}$` 的条目整条拒收，进 `rejected`，不写库。
- token 不对 `401`；服务端未配置 token `503`；超过 500 条 `400`。

### 11.4 归属判断

**用 UP主 mid 白名单判断「这条视频是不是帅哥录屏的」，不是用「`video_source` 里有没有这个 bvid」。**

因为台账漏记了 21 条线上稿件：按表判断会让这 21 条整块不显示，按 mid 判断则统一显示「出处还在整理」。

配置项（管理后台可改）：

| 配置 | 说明 |
|:--|:--|
| `repost_up_mid` | 帅哥录屏 B站 UID（现为 `3707052465589015`），支持逗号分隔多个；为空则任何视频都不显示该区块 |
| `repost_account_name` | 区块显示的账号名，默认「帅哥录屏」 |
| `repost_account_avatar_url` | 账号头像 URL（转存 COS，不硬编码在小程序里） |
| `source_ingest_token` | 上报接口鉴权 token |

### 11.5 解析结果字段

`POST /api/parse` 响应新增 `origin`（与表示收藏来源的 `source` 字段无关）：

```json
{
  "origin": {
    "account_name": "帅哥录屏",
    "account_avatar_url": "https://.../avatar.jpg",
    "platform": "douyin",
    "platform_label": "抖音",
    "author_name": "小山坡",
    "author_url": "https://www.douyin.com/user/MS4wLjABAAAA..."
  }
}
```

- `origin = null` → 前端**整块不渲染**。
- `origin` 有值但字段为空 → 显示「整理中 / 待补充」。
- 「复制原up账号」复制的是 `author_handle`（唯一、可搜索），没有才退回昵称；
  X / YouTube 的 handle 服务端可从主页链接推导，抖音号必须由上报方提供。

### 11.6 前端展示

解析结果页在「基本信息」之后插入一张卡片，三种状态共用同一套样式：

```text
① 能查到                             ② 还在整理
▍(头像) 帅哥录屏 · 原up主是谁 [粉丝专属]  ▍(头像) 帅哥录屏 · 原up主是谁 [粉丝专属]
原平台　抖音                          原平台　—
原up主　@小山坡          复制主页       原up主　—
                                     这条的出处还在整理，稍后再来看看

③ 只知道平台（14 条）：原平台　抖音 / 原up主　待补充
```

- 标题用粉丝原话「帅哥录屏 · 原up主是谁」，账号名出现在标题里，感知是「账号把出处告诉我了」，
  而不是「小程序能解析出处」；`up主` 按页面现有写法用小写。
- 字段沿用 `field` 的「字段名 / 值」结构；「复制主页」与「标题 / up主」行的「复制」同一位置、
  同一 `class="action"`、同一处理方式。
- 不提供「复制原视频链接」，不做跳转（抖音链接在小程序里打不开）。
- 文案避免「搬运」二字（带二次上传意味），用「原up主 / 原平台」。
