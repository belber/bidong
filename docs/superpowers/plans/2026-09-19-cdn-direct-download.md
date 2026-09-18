# B站 CDN 直连下载改造方案

> 状态：待评审

## 1. 目标

把视频/音频下载从「后端中转流量」改成「后端解析直链、小程序前端直接下载」，同时解决三个问题：

1. 前端直接下载 B站 CDN 直链，不再消耗后端服务器流量。
2. 管理端能看清下载成功率、失败原因、域名是否配置。
3. 用户下载失败时有可操作的兜底方案（复制链接到微信手动保存）。

## 2. 总体流程

```text
用户点击下载
  -> 请求后端 /download-url?kind=...&qn=...
  -> 后端调用 B站 playurl，返回候选 CDN 直链列表
  -> 后端自动登记出现过的域名
  -> 小程序用 wx.downloadFile 依次尝试候选链接
  -> 成功：视频保存相册 / 音频转发文件
  -> 失败：上报事件 + 弹窗兜底
```

## 3. 范围边界

第一期只开放：

- `watermarked` 水印视频：`fnval=1&platform=html5`，完整 MP4。
- `audio` 纯音频：DASH 音频轨 `.m4s`，下载后按 `.m4a` 转发。

`clean` 无水印视频暂不支持，原因是 DASH 视频轨不含音频，需要合流。功能开关保持关闭，前端不展示入口。

## 4. 后端改动

### 4.1 数据模型

新增两张表。

`bili_cdn_domain`：

```text
id
host
is_configured
first_seen_at
last_seen_at
seen_count
download_success_count
download_failure_count
notes
created_at
updated_at
```

`download_event`：

```text
id
user_id
card_id
bvid
kind
qn
host
candidate_index
stage        # resolve / download / save / share
status       # success / fail
error_type
error_message
http_status
wx_err_msg
created_at
```

签名 URL 不落库，只落 host 和错误摘要。

### 4.2 `/api/cards/{id}/download-url` 改造

返回从单 URL 改为候选列表：

```json
{
  "kind": "watermarked",
  "qn": 16,
  "expires_at": 1789752728,
  "candidates": [
    {
      "url": "https://upos-sz-mirrorcoso1.bilivideo.com/a.mp4?...",
      "host": "upos-sz-mirrorcoso1.bilivideo.com",
      "configured": false
    },
    {
      "url": "https://upos-sz-estgcos.bilivideo.com/b.mp4?...",
      "host": "upos-sz-estgcos.bilivideo.com",
      "configured": true
    }
  ]
}
```

规则：

- 水印视频：`fnval=1`，`platform=html5`。
- 音频：`fnval=16`，不传 `platform=html5`，避免 B站返回空 DASH。
- 候选顺序：主地址，然后 backup 地址。
- 按 host 去重。
- 自动登记 host 到 `bili_cdn_domain`，更新 `seen_count` 和 `last_seen_at`。
- 动态 PCDN 域名（如 `xy*.mcdn.bilivideo.cn:8082`）跳过，不返回给前端。

### 4.3 `/api/download-events` 上报接口

登录用户 POST 一条下载事件。后端写入 `download_event`，并根据 host 更新域名表的成功/失败计数。

### 4.4 管理端接口

`GET /api/admin/stats/download`：

```json
{
  "total": 0,
  "success": 0,
  "fail": 0,
  "success_rate": 0,
  "by_stage": [],
  "fail_by_error": [],
  "fail_by_host": [],
  "trend": []
}
```

`GET /api/admin/stats/download/detail`：分页明细。

`GET /api/admin/download/domains`：域名列表。

`PUT /api/admin/download/domains/{host}`：标记是否已配置到微信后台。

## 5. 前端改动

### 5.1 结果页不再预下载音频

当前结果页进入时就会预下载音频，这与「音频不走后端流量」冲突。改为用户点「转发」时再取直链并下载。

### 5.2 新增 `miniprogram/utils/mediaDownload.js`

职责：

- 按候选顺序调用 `wx.downloadFile`。
- 每个候选失败后自动尝试下一个。
- 下载成功返回 `tempFilePath`。
- 每个阶段通过回调上报事件。
- 错误分类：
  - `domain_not_configured`：微信报 url not in domain list。
  - `expired`：HTTP 403。
  - `http_error`：其他 4xx/5xx。
  - `wx_error`：微信 downloadFile 失败。
  - `unknown`。

### 5.3 结果页下载交互

水印视频：

```text
选择清晰度
  -> 请求 download-url
  -> 尝试候选下载
  -> 保存相册
  -> 上报 resolve/download/save
```

纯音频：

```text
点击转发
  -> 请求 download-url
  -> 尝试候选下载
  -> 复制为 .m4a 文件
  -> wx.shareFileMessage 转发
  -> 上报 resolve/download/share
```

### 5.4 失败兜底弹窗

下载失败后弹窗提供：

1. 复制下载链接。
2. 查看手动保存教程。
3. 重新解析。

教程合并写一套通用步骤，再补充 Android/iOS 差异。

## 6. 管理端页面

### 6.1 下载监控

展示：

- 下载总数、成功、失败、成功率。
- 下载趋势。
- 失败原因分布。
- 失败域名分布。
- 明细列表。

### 6.2 B站域名管理

展示每个域名：

- host。
- 是否已配置到微信后台。
- 出现次数。
- 下载成功/失败次数。
- 最近出现时间。
- 状态建议。

排序优先级：

1. 未配置且已出现。
2. 下载失败率高。
3. 已配置但建议删除。
4. 已配置且正常使用。

闲置提醒：

```text
30 天未出现 -> 可能闲置
60 天未出现 -> 建议删除
```

系统只提醒，不自动删除微信后台配置。

## 7. 微信后台配置

B站 CDN 直链必须配置在 `downloadFile合法域名`，不是 `request合法域名`。

自有 API 仍配置在 `request合法域名`。

首批建议配置域名：

```text
upos-sz-mirrorcoso1.bilivideo.com
upos-sz-estgcos.bilivideo.com
upos-sz-mirrorcos.bilivideo.com
upos-sz-mirrorcosb.bilivideo.com
upos-sz-mirrorhwb.bilivideo.com
upos-sz-mirrorhw.bilivideo.com
upos-sz-mirrorbd.bilivideo.com
upos-sz-mirrorali.bilivideo.com
upos-sz-mirroralib.bilivideo.com
upos-sz-estgoss.bilivideo.com
upos-sz-mirrorzos.bilivideo.com
upos-sz-mirror14b.bilivideo.com
```

后续以管理端「未配置且已出现」为准继续补充。

## 8. 测试计划

后端 pytest：

- download-url 水印返回候选列表并登记域名。
- download-url 音频不带 `platform=html5`，能拿到音频轨。
- 事件上报写入并更新域名计数。
- 管理端下载统计/明细。
- 管理端域名列表/更新。

前端 jest：

- 错误分类。
- 候选域名提取。
- 候选依次尝试，全部失败 reject。

## 9. 验证与提交

- 后端 `pytest` 全绿。
- 前端 `jest` 全绿。
- 只提交本次相关文件，不碰工作区已有的 logo 删除和 `docs/审核问答话术.md`。

## 10. 待你确认的决策点

1. 闲置提醒用 `30/60 天` 还是 `60/90 天`？
2. 音频 `.m4s` 下载后改名为 `.m4a` 转发，这个需要在真机上验证能否播放；是否先按这个方案做？
3. 下载失败兜底弹窗，除了「复制链接 / 教程 / 重新解析」，是否还需要「联系客服」入口？
