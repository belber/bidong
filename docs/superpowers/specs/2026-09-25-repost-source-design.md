# 「视频出处（原up主）」设计文档

> 状态：已评审 ｜ 日期：2026-09-25 ｜ 代号：repost-source

## 0. 一句话定位

给 B站账号「帅哥录屏」的粉丝看的溯源信息：在小程序**解析结果页**多出一块
「帅哥录屏 · 原up主是谁」，写明这条视频**从哪个平台、搬自谁**。该区块**只出现在帅哥录屏自己的稿件上**，
其他 UP 主的视频解析结果页完全不变。

## 1. 背景与问题

- 帅哥录屏是转载号，粉丝常在评论区问「出处是哪里、原 up 主是谁」。
- 家中小主机（Hermes）用脚本自动发布，并维护一份 Markdown 台账 `bili_台账.md`，
  但台账**从来没有记录原作者**，只有源链接（68% 有）和博主名（零散写在括号里）。
- 账号置顶评论在引导粉丝使用「壁咚咚藏链阁」小程序，所以这个溯源信息放在小程序里最合适。

## 2. 数据源现状（实测）

| 项 | 值 |
|:--|:--|
| 线上稿件 | 192 条 |
| 台账有 BVID | 182 条（95%） |
| 能回填出「平台 + 作者」 | 110 条（57%） |
| 只有平台、没有作者 | 14 条（抖音老链接 404/400） |
| 完全查不到出处 | 68 条（35%） |

回填产物：`台账_出处回填_全量.csv`，124 行，字段见 §4.2。

**结论（Hermes 提出、已采纳）：** 不解析 Markdown 台账（有脚注、重复编号、缺号、写法不统一）；
改为**发布时顺手落一行结构化数据**，发布流程本来就要解析源链接，作者信息是现成的。

## 3. 架构

```text
Hermes（家里小主机）
  发布视频 → 解析源链接 → 顺手 append 一行到 sources.jsonl
                                  │  POST（X-Ingest-Token）
                                  ▼
腾讯云服务器 FastAPI
  POST /api/sources/ingest  →  按 bvid 幂等 upsert
                                  ▼
                            video_source 表（全局共用，不按用户分）
                                  ▲
  小程序 POST /api/parse ──────────┘  查 bvid 的出处
        │
        └─ 该视频 UP主 mid 命中白名单 → ParseResult.origin 有值 → 结果页渲染专属区块
```

**为什么用 HTTP 而不是 scp 文件同步：** scp 需要在家里那台自动发视频的机器上配服务器 SSH 密钥，
等于给它开一个能写服务器的后门。HTTP 只给一个只能写一张表的 token，出问题影响面小，
字段还能在写入口校验（台账质量已知很脏）。

## 4. 数据契约

### 4.1 上报字段

| 字段 | 类型 | 必填 | 说明 |
|:--|:--|:--|:--|
| `bvid` | string | ✅ | B站视频号，**唯一键**，形如 `BV15Pbj6yEKg` |
| `title` | string | | B站标题 |
| `platform` | string | | `douyin` / `x` / `youtube` / `kuaishou` / `xiaohongshu` / `weibo` / `bilibili` / `other` / `unknown` |
| `author_name` | string | | 原作者昵称 |
| `author_id` | string | | 原作者稳定 ID（昵称会改，用它关联） |
| `author_url` | string | | 原作者主页 |
| `source_url` | string | | 源视频链接 |
| `source_video_id` | string | | 源站视频 ID |
| `bili_published_at` | string | | B站发布日 `YYYY-MM-DD`（源站发布时间拿不到） |
| `note` | string | | 拿不到时的原因，如 `parse失败 404` |

**约定：** 拿不到就留空并在 `note` 写明原因，**不要猜**。一条视频只报一条「主要出处」= 画面来源；
混源视频（画面来自 X、BGM 来自抖音）只报画面来源。

### 4.2 存储表 `video_source`

```sql
video_source (
  id                PK,
  bvid              text unique,   -- 唯一键
  title             text default '',
  platform          text default '',
  author_name       text default '',
  author_id         text default '',
  author_url        text default '',
  source_url        text default '',
  source_video_id   text default '',
  bili_published_at text default '',   -- YYYY-MM-DD
  note              text default '',
  created_at        timestamp,
  updated_at        timestamp
)
```

**全局共用一张表**，不按用户冗余：同一条视频的出处对所有用户都一样。

## 5. 接口

### 5.1 出处上报（小主机 → 后端）

`POST /api/sources/ingest`，请求头 `X-Ingest-Token: <token>`。

请求体接受三种形态：`{"items":[...]}`、单个对象 `{...}`、或数组 `[...]`；单次最多 500 条。

```json
{
  "items": [
    {
      "bvid": "BV15Pbj6yEKg",
      "title": "【小视频】126-减脂只是为了多吃",
      "platform": "douyin",
      "author_name": "小山坡",
      "author_id": "MS4wLjABAAAA...",
      "author_url": "https://www.douyin.com/user/MS4wLjABAAAA...",
      "source_url": "https://v.douyin.com/Ou--3FzQeWs/",
      "source_video_id": "7681665368289533561",
      "bili_published_at": "2026-09-05",
      "note": ""
    }
  ]
}
```

响应：

```json
{"ok": true, "created": 12, "updated": 3, "rejected": [{"bvid": "xxx", "reason": "invalid bvid"}]}
```

- 按 `bvid` 幂等：重复上报是覆盖更新，所以**重发永远安全**。
- `bvid` 不合法（不匹配 `^BV[0-9A-Za-z]{10}$`）的条目整条拒收，进 `rejected`，不写库。
- token 不对 → `401`；服务端未配置 token → `503`；超过 500 条 → `400`。

### 5.2 解析结果新增字段

`POST /api/parse` 的响应新增 `origin`：

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

- `origin = null` → 前端**整块不渲染**（不是帅哥录屏的视频）。
- `origin` 有值但字段为空 → 前端显示「整理中 / 待补充」。

`origin` 与现有 `source` 字段（`local` / `robot` 收藏来源）**是两个概念**，不要混。

## 6. 识别规则

**判断「这条视频是不是帅哥录屏的」用 UP主 mid 白名单，而不是「表里有没有这个 bvid」。**

原因：台账漏记了 21 条线上稿件。若按表判断，这 21 条会被当成别人的视频、整块不显示；
按 mid 判断则统一显示成「出处还在整理」——粉丝体验一致，运营也能看出漏了哪些。

配置项（管理后台可改）：

| 配置 | 说明 |
|:--|:--|
| `repost_up_mid` | 帅哥录屏的 B站 UID（`3707052465589015`），支持逗号分隔多个 |
| `repost_account_name` | 区块上显示的账号名，默认「帅哥录屏」 |
| `repost_account_avatar_url` | 账号头像 URL（转存到 COS，不硬编码在小程序里） |
| `source_ingest_token` | 上报接口鉴权 token |

白名单为空 → 任何视频都不显示该区块。

## 7. 前端

解析结果页在「基本信息」卡片之后插入一张卡片，三种状态共用同一套样式：

```text
① 能查到：                          ② 还在整理：
▍(头像) 帅哥录屏 · 原up主是谁 [粉丝专属]   ▍(头像) 帅哥录屏 · 原up主是谁 [粉丝专属]
原平台　抖音                          原平台　—
原up主　@小山坡          复制主页        原up主　—
                                     这条的出处还在整理，稍后再来看看
```

③ 只知道平台、不知道是谁（14 条）：`原平台　抖音` / `原up主　待补充`。

- 标题用**粉丝的原话**：「帅哥录屏 · 原up主是谁」；账号名出现在标题里，
  让用户感知是「这个账号把出处告诉我了」，而不是「小程序能解析出处」。
- 字段用现有 `field` 的「字段名 / 值」结构；「复制主页」与「标题 / up主」行的「复制」
  同一位置、同一 `class="action"`、同一处理方式。
- 不提供「复制原视频链接」（只要主页），不做跳转（抖音链接在小程序里打不开）。
- 文案避免「搬运」二字，它带二次上传意味；用「原up主 / 原平台」。

## 8. 测试

- 后端：上报接口的鉴权（401 / 503 / 正确 token）、幂等 upsert、批量、非法 bvid 拒收、超 500 条拒绝；
  解析结果在白名单命中且有记录 / 命中但无记录 / 未命中三种情况下的 `origin`。
- 前端：三种状态的渲染、「复制主页」调用与 toast、`origin` 为空时不渲染该卡片。

## 9. 明确不做

- 混源视频的多出处（只记画面来源一条）
- 到原平台的跳转（只复制主页）
- 解析 Markdown 台账作为生产数据源
- 按用户维度存出处（全局共用一张表）

## 10. 遗留风险

| 风险 | 说明 |
|:--|:--|
| 抖音通道不稳定 | Hermes 侧依赖 douyin.wtf 公共 demo，会限流/失效；失败时留空 + `note` |
| 历史覆盖率 | 35% 老视频短期内只能显示「整理中」 |
| 白名单漏配 | `repost_up_mid` 为空则整块不显示，部署后必须确认已配置 |
