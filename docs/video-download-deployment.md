# 完整视频下载与封面缩略图

解析页概览使用 `cover_url` 缩略图，点击预览；缺失或加载失败时显示占位。长标题最多三行，完整标题保留在“更多信息”。媒体区只有一个“视频下载”入口，遵守原无水印开关；音频和抖音图集保持独立。默认不启动文案识别。

## 本地启动

在 `server` 执行 `.venv/bin/python -m alembic upgrade head` 后运行 `./dev.sh`。脚本同时管理 API、管理端、机器人、文案 worker 和新增视频 worker，Ctrl+C 统一停止。手动启动独立 worker：`.venv/bin/python -m app.video_download_worker`。修改 Python worker 代码后需重启，API reload 不会重启 worker。

## Compose

`server/docker-compose.yml` 增加 `video-download`，限制 1 CPU、256MiB。API 与 worker 必须共享 `video_download_cache` 卷及 `VIDEO_DOWNLOAD_CACHE_DIR=/video-downloads`，否则 API 无法读取准备完成的文件。镜像已有 FFmpeg。迁移成功后再启动服务；本次不自动部署生产。

环境变量及默认值见 `server/.env.example` 的 `VIDEO_DOWNLOAD_*`。本地可以留空 `VIDEO_DOWNLOAD_FFMPEG_BIN`，回退到 `TRANSCRIPT_FFMPEG_BIN`。Compose 固定使用镜像的 `ffmpeg`。原生 macOS 的 dev.sh 不提供容器资源硬限制；服务器硬限制由 Compose 生效。

## 接口与行为

- `GET /api/cards/{id}/media-options?kind=video` 只返回可生成完整视频的清晰度，原清晰度接口类型继续兼容。
- 登录后 `POST /api/cards/{id}/video-download`，请求体 `{ "qn": 80 }`（可省略清晰度）。同清晰度有完整 MP4 则直接返回 CDN candidates；否则入队，返回 202。
- `GET /api/cards/{id}/video-download` 返回最新任务。可附 `qn` 查询特定清晰度；查询本身不创建任务。状态 `idle / queued / processing / ready / failed / expired`。
- `ready` 的 `mode=direct` 使用 CDN；`mode=file` 使用返回的相对 `file_url`，下载必须附带原登录 Authorization。始终检查卡片和任务归属，不生成公开缓存链接。
- 分轨仅接受 H.264 + AAC，FFmpeg 流复制为 MP4；无兼容流时明确拒绝该清晰度，不降低清晰度或重新编码。源数据确认没有音轨才允许无声结果并提示“原视频无声音”；任何音轨请求失败均失败。
- “无水印”使用平台提供的干净流，不删除作者已嵌入画面的 Logo、字幕等。

## 队列与磁盘

数据库单行锁串行提交、领取，支持 SQLite/PostgreSQL；不使用 Redis。全局准备一个任务，每用户一个未完成任务，最多十个等待任务。相同用户、作品、分 P、清晰度复用任务。worker 每十秒续租，崩溃过期后最多自动恢复一次。

需要服务器处理的合计输入最多 512MiB、超时十分钟。CDN 直下不受这些合并限制。流式下载逐块检查实际大小，临时输入在成功、失败、超时均清除；异常停机留下的目录在超时加租约后自动清理。准备前检查磁盘，预留输入和输出空间。实际下载进度在客户端展示，准备阶段只显示“准备中，可稍后回来”。用户返回页面只查询状态，不重复启动任务。

准备文件默认缓存三十分钟，总上限 2GiB，先清过期，再按到期时间淘汰未使用文件。文件下载申请时保护十五分钟，防止下载中被淘汰。worker 空闲轮询也执行清理。缓存丢失或被淘汰后返回 expired，可重新准备。服务停机期间不执行清理，重启 worker 后恢复。

## 验收说明

自动化覆盖接口权限、开关、幂等、队列、缓存、真实 FFmpeg 合并及媒体解码。真实平台访问可能因 Cookie、限流或 CDN 白名单失败；本地媒体合并测试不能代表真实平台验收通过。微信开发者工具截图和测试记录另附交付报告。
