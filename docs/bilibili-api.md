# B站公开 API 清单 · 视频解析字段说明

> 目的：明确「壁咚视频助手」能做哪些功能——哪些接口要登录、哪些不用，以及视频到底能解析到哪些信息。
>
> **一句话结论**：解析 / 读取类接口基本**无需登录**；一切写操作（发评论、发私信、投稿）**一律需要登录态 Cookie**，且属高风险（WAF、限流、短信验证）。
>
> 文末第六章是你要的「视频能解析到的信息 ↔ 接口 ↔ 字段」总表。

---

## 图例

| 标记 | 含义 |
|---|---|
| ✅ | 无需登录，匿名可调 |
| 🔐 | 需要登录态 Cookie（SESSDATA 等） |
| 🔏 | 需要 wbi 签名（可匿名拿签名，但接口本身已加签） |
| 🚫 | 写操作 / 高风险（WAF 406、601/21615 限流、短信验证码） |

---

## 一、账号 / 用户 / 查重（含机器人账号）

先说明一个关键认知：**B站没有「机器人账号」这种官方类型**。我们说的「@壁咚收藏夹 机器人」，本质就是一个**普通 B站账号**，靠后台持有它的登录态 Cookie 去「收私信、解析 @ 指令、发评论回复」。所以「查机器人账号」就是「查一个普通账号」，用下面同一套接口。

### 1.1 按昵称搜索用户（查重 / 查账号是否存在）✅

```bash
curl "https://api.bilibili.com/x/web-interface/search/type?search_type=bili_user&keyword=壁咚收藏夹"
```

- 用途：起名时查这个昵称是否已被人占用（就是之前用来验证「壁咚收藏夹」是否可用、以及看别人机器人怎么命名的接口）。
- 返回：`data.result[]`，每项含 `uname`（昵称）、`mid`（UID）、`usign`（签名）。
- 判断：搜不到精确同名 → 大概率可用；搜到 → 已占用。

### 1.2 按 UID 查用户主页信息 ✅

```bash
curl "https://api.bilibili.com/x/space/acc/info?mid={UID}"
```

- 返回：`data.name`（昵称）、`data.face`（头像）、`data.sign`（签名）、`data.level` 等。
- 用途：机器人绑定时，用激活码换取用户提供的 `bili_uid` 后，反查确认这个 UID 是真实账号。

### 1.3 关注 / 粉丝统计 ✅

```bash
curl "https://api.bilibili.com/x/relation/stat?vmid={UID}"
```

- 返回：`data.follower`（粉丝数）、`data.following`（关注数）。

---

## 二、视频解析（读，无需登录）—— 产品核心

### 2.1 视频详情 `view` ✅（最重要，一个接口拿全）

```bash
curl "https://api.bilibili.com/x/web-interface/view?bvid=BV1xxxx"
```

- 返回码 `code:0` 即成功，无需登录。
- 一个接口就能拿到封面 / 标题 / UP主 / 分区 / 简介 / 数据统计，是「贴链接解析」的基石。

**返回的 `data` 字段（收藏功能用得到的）：**

| 字段路径 | 含义 | 示例 |
|---|---|---|
| `data.title` | 标题 | 一口气看懂《三体》黑暗森林 |
| `data.pic` | 封面图 URL | //i0.hdslb.com/...jpg |
| `data.bvid` / `data.aid` | bv号 / av号 | BV1xxxx / 123456 |
| `data.owner.name` | UP主昵称 | 木鱼水心 |
| `data.owner.mid` | UP主 UID | 1234567 |
| `data.owner.face` | UP主头像 | //i1.hdslb.com/...jpg |
| `data.tname` / `data.tid` | 分区名 / 分区id | 影视 / 181 |
| `data.desc` | 简介 | ... |
| `data.duration` | 总时长（秒） | 2712（=45:12） |
| `data.pubdate` | 发布时间（unix 秒） | 1754000000 |
| `data.cid` | 首P 的 cid（弹幕/字幕要用） | 987654 |
| `data.videos` | 分P 数 | 1 |
| `data.stat.view` | 播放量 | 123456 |
| `data.stat.like` / `coin` / `favorite` / `share` | 点赞/投币/收藏/分享 | ... |
| `data.stat.danmaku` / `reply` | 弹幕数 / 评论数 | ... |
| `data.pages[]` | 分P列表（cid/part/duration） | ... |
| `data.staff[]` | 联合投稿成员 | ... |

### 2.2 弹幕（读）✅

```bash
curl -H "Accept-Encoding: gzip" "https://api.bilibili.com/x/v1/dm/list.so?oid={cid}"
```

- **返回 XML，且 gzip 压缩**，要先解压再解析。
- 结构：根节点 `<i>`，每条弹幕 `<d p="...">弹幕文本</d>`。
- `p` 属性逗号分隔：`时间,模式,字号,颜色,时间戳,弹幕池,用户hash,dmid`。
- 用途：解析出弹幕内容做「字幕/金句」或热度分析。

### 2.3 评论（读）✅

```bash
curl "https://api.bilibili.com/x/v2/reply?type=1&oid={aid}&pn=1&ps=20"
```

- 返回：`data.replies[]`，每项 `member.uname`（用户）、`content.message`（评论内容）。
- 用途：读评论没问题；**发评论见第四章，需登录**。

### 2.4 字幕 🔏

```bash
curl "https://api.bilibili.com/x/player/wbi/v2?bvid={BV}&cid={cid}&w_rid={...}&wts={...}"
```

- **已加 wbi 签名**，需先按第五章的 wbi 算法拼 `w_rid` / `wts`。
- 返回：`data.subtitle.subtitles[]`，每项 `lan`（语言）、`lan_doc`（语言名）、`subtitle_url`（字幕文件地址，下载后是 .json 格式）。
- 用途：「字幕摘要 / 金句」类功能。

---

## 三、机器人账号的读写接口（需登录 🔐）

机器人 = 普通账号 + 登录态 Cookie，核心是「收私信 → 解析 @ 指令 → 回复/收藏」。

### 3.1 私信会话列表（监听 @ 消息）🔐

```bash
curl -b "SESSDATA=...; bili_jct=..." \
  "https://api.vc.bilibili.com/session_svr/v1/session_svr/get_sessions?session_type=1"
```

- 用途：轮询有没有新私信（用户 @机器人 + 链接 + #标签）。
- 注意：B站私信接口随版本变动较多，**上线前需实测当前可用版本**。

### 3.2 未读私信数 🔐

```bash
curl -b "SESSDATA=..." \
  "https://api.vc.bilibili.com/session_svr/v1/session_svr/single_unread?session_type=1"
```

### 3.3 发送私信（机器人回复）🔐🚫

```bash
curl -b "SESSDATA=...; bili_jct=..." -X POST \
  -d "msg[sender_uid]=机器人UID&msg[receiver_id]=对方UID&msg[content]=已收藏&msg[msg_type]=1&csrf=bili_jct值" \
  "https://api.vc.bilibili.com/web_im/v1/web_im/send_msg"
```

- `csrf` 参数 = cookie 里的 `bili_jct` 值。

### 3.4 发评论（机器人「评论 @」场景）🔐🚫

```bash
curl -b "SESSDATA=...; bili_jct=..." -X POST \
  -d "type=1&oid={aid}&message=...&csrf=..." \
  "https://api.bilibili.com/x/v2/reply/add"
```

- **未登录时返回 `code:-101`**（实测验证过）——这是「评论必须登录」的铁证。

### 3.5 检测新粉丝 + 关注自动回激活码 🔐🚫

> 「用户关注机器人 → 自动回激活码」**没有现成回调 API**，用两个接口拼：轮询检测新粉丝 → 发私信回激活码。

**① 检测新粉丝（通知流，推荐）🔐**

```bash
curl -b "SESSDATA=..." \
  "https://api.bilibili.com/x/msgfeed/follow"
```

- 返回 `data.items[]`，每条一条「新粉丝」通知：`user.mid`（新粉丝 UID）、`user.uname`（昵称）、`time`（关注时间 unix 秒）、`id`（通知 id，去重用）。
- 轮询逻辑：记录已处理的最大 `id`/`time`，只对「新出现的」粉丝发码。
- ⚠️ 字段以实测为准（同私信接口，版本变动较多）。

**② 兜底：粉丝列表做差集 ✅**

```bash
curl "https://api.bilibili.com/x/relation/followers?vmid={机器人UID}&pn=1&ps=50"
```

- 匿名可读，但只能翻有限页，新粉丝多时易漏，不如通知流干净。

**③ 回送激活码 🔐🚫**

用 3.3 的发私信接口：`msg[receiver_id]` 填 `user.mid`、`msg[content]` 填激活码。

**必做防御（防刷码 / 防风控）：**

- **幂等去重**：同一 `user.mid` 只发一次（服务端记录已发 UID）。
- **控频**：发送间隔拉长（每账号 ≥ 数秒），别刚关注就秒发。
- **一次性激活码**：绑定后即失效，防「取关 → 再关注」刷码。

---

## 四、发布 / 投稿（需要登录，最高风险 🚫）

> 与「下载抖音/X 视频再发到 B站」那条线相关（Hermes 项目）。这条线法律风险高（bilibili-api 库已因律师函归档），**壁咚 MVP 先不做**，仅记录。

- 上传：Playwright 自动化 `member.bilibili.com` 上传页，抓取上传成功后的文件名。
- 提交：`POST member.bilibili.com/x/vu/web/add/v3`（老版 `add`）。
- 风险：WAF 406、`601`/`21615` 限流、短信验证码；Cookie 2–7 天过期。

---

## 五、登录态获取与 wbi 签名

### 5.1 二维码登录（获取机器人账号 Cookie）🔐

```bash
# 生成二维码
curl "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
# → data.url（二维码内容）, data.qrcode_key

# 轮询扫码状态
curl "https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={key}"
# code 0=成功(拿到Cookie) / 86038=未扫 / 86090=已扫未确认
```

- 拿到后必须保存的 Cookie 字段：`SESSDATA`（登录态）、`bili_jct`（csrf token）、`DedeUserID`、`buvid3`、`buvid4`。

### 5.2 wbi 签名 🔏（字幕等加签接口需要）

1. `GET /x/web-interface/nav` → 取 `data.wbi_img.img_url`、`sub_url` 的文件名（去掉扩展名）作为 `img_key`、`sub_key`。
2. 用固定数组 `mixinKeyEncTab` 按 `img_key+sub_key` 重排取 32 位 → `mixin_key`。
3. 请求参数追加 `wts`（当前 unix 秒）→ 按 key 排序 → URL 编码 → 过滤 `!'()*` → 拼 `mixin_key` → MD5 得 `w_rid`。

> 实现时建议用现成库（如 `bilibili-api-python` 的 fork，或社区维护的 wbi 工具函数），别手写 MD5 表。

---

## 六、总表：视频能解析到的信息 ↔ 接口 ↔ 字段

> 这是「贴链接 → 解析」这一步的能力上限。收藏卡片需要的字段，`view` 一个接口就全了。

| 视频信息 | 接口 | 字段路径 | 登录 |
|---|---|---|---|
| 标题 | `x/web-interface/view` | `data.title` | ✅ |
| 封面图 | `x/web-interface/view` | `data.pic` | ✅ |
| bv号 / av号 | `x/web-interface/view` | `data.bvid` / `data.aid` | ✅ |
| UP主昵称 | `x/web-interface/view` | `data.owner.name` | ✅ |
| UP主 UID | `x/web-interface/view` | `data.owner.mid` | ✅ |
| UP主头像 | `x/web-interface/view` | `data.owner.face` | ✅ |
| 分区名 / id | `x/web-interface/view` | `data.tname` / `data.tid` | ✅ |
| 简介 | `x/web-interface/view` | `data.desc` | ✅ |
| 时长（秒） | `x/web-interface/view` | `data.duration` | ✅ |
| 发布时间 | `x/web-interface/view` | `data.pubdate` | ✅ |
| 播放 / 点赞 / 投币 / 收藏 / 分享 | `x/web-interface/view` | `data.stat.*` | ✅ |
| 弹幕数 / 评论数 | `x/web-interface/view` | `data.stat.danmaku` / `reply` | ✅ |
| 分P 列表 | `x/web-interface/view` | `data.pages[]` | ✅ |
| 联合投稿成员 | `x/web-interface/view` | `data.staff[]` | ✅ |
| 弹幕内容 | `x/v1/dm/list.so?oid={cid}` | XML `<d p="...">` | ✅（gzip） |
| 评论内容 | `x/v2/reply?type=1&oid={aid}` | `data.replies[].content.message` | ✅ |
| 字幕文件 | `x/player/wbi/v2` | `data.subtitle.subtitles[].subtitle_url` | 🔏 |
| 视频流下载地址 | 不公开 / 需登录 + 风控 | — | 🔐🚫 |

**结论**：收藏卡片所需（封面 / 标题 / UP主 / 分区 / 简介 / 时长 / 数据）**全部无需登录**，`view` 接口一次拿全；弹幕 / 评论可匿名读；字幕要 wbi 签名；一切写操作（发评论 / 私信 / 投稿）都要登录态 Cookie。

---

## 七、给「壁咚」的功能边界建议（基于上面清单）

| 想做 | 是否可行 | 依据 |
|---|---|---|
| 贴链接解析收藏（封面/标题/UP主/分区/时长） | ✅ 稳 | `view` 无需登录 |
| 弹幕 / 评论读取（金句、热度） | ✅ 稳 | 匿名可读 |
| 字幕摘要 | ⚠️ 可行但加签 | `player/wbi/v2` 需 wbi |
| @机器人 收私信 → 自动入收藏 | 🔐 需登录 + 轮询 | 私信接口需 Cookie |
| 关注 → 自动回激活码 | 🔐🚫 需登录 + 控频 | `msgfeed/follow` 检测 + 私信回复 |
| 机器人发评论回复 | 🔐🚫 高风险 | 需登录，易触发风控 |
| 下载视频 / 投稿发布 | 🚫 法律 + 风控双高 | bilibili-api 已归档，先不做 |

> 下一步写 spec 时，会把「机器人收私信 → 自动收藏」明确为需要「后台持有机器人账号登录态 Cookie」这一前置条件。
