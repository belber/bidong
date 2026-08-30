# AGENTS.md

## 项目

**B站视频收藏助手**（代号 bili-collector）：微信原生小程序，把 B站视频存成「卡片」（标题 / 封面 / UP主 / 分区），用标签归类，按收藏月份分组，点击跳回 B站查看。

只存元数据 + 转存后的缩略图，不播视频、不存视频本体。

## 仓库结构

- `docs/` — 设计文档（spec.md、bilibili-api.md、prototype.html、logo 方案）
- `miniprogram/` — 微信原生小程序（Phase 0 前端）
- `server/` — Python FastAPI 后端（Phase 0 后端）

## 技术栈

- 前端：微信原生小程序
- 后端：Python FastAPI
- 数据库：PostgreSQL
- 对象存储：腾讯云 COS（缩略图转存）
- 部署：腾讯云轻量服务器 + 域名 + ICP 备案

## 架构原则

- 后端是纯 REST API，与前端无关；未来 APP/PC Web 只重写前端，后端复用。
- B站接口统一走后端（反爬需固定 IP + UA）；封面 `http://` 且防盗链，必须下载转存，不能直接外链。

## 核心决策（详见 docs/spec.md）

- 「分组」不单独建模，就是一种标签。
- 月份分组由 `collected_at` 派生，冗余存 `month`（YYYY-MM），与标签正交。
- Phase 1 机器人触发：B站机器人账号轮询私信/@，激活码绑定 UID，`@机器人 + 链接 + #标签` → 自动存到对应收藏夹。

## 里程碑顺序

1. **Phase 0（核心闭环）**：后端地基（FastAPI 骨架 + `/api/parse` + 存库 + 缩略图转存）→ 前端骨架（贴链接 → 解析 → 卡片展示）→ 前端完成（月份分组 + 标签 + 微信登录）→ 部署 → 提审发布
2. **Phase 1（机器人触发）**：机器人账号 + 私信监听 worker → 激活码 + 绑定体系 → @ 指令解析 + 自动收藏 → 小规模上线

## 约定

- 重要设计变更先更新 `docs/spec.md`。
- 后端接口路径见 spec.md §6，保持 REST 风格。
