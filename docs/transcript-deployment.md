# 视频文案部署与验收

文案是按需功能，解析和普通下载不下载识别音轨、不运行VAD或Whisper。
只面向口播/讲解；VAD并不能可靠地区分唱歌与说话。识别内容仅供参考。

默认引擎为SenseVoice INT8，Whisper保留为可选回退。VAD和识别各自在独立子进程运行。

## 云服务器（2核2GB）

1. 更新代码后，按现有流程构建镜像并运行迁移。镜像编译固定的 whisper.cpp v1.8.2（CPU），包含FFmpeg和ONNX运行时。首次构建较慢，编译并发为1；后续使用Docker构建缓存。
2. 初始化模型（不用等API启动、不把模型写进Git）：

```bash
cd server
APP_ENV_FILE=.env.prod docker compose build
APP_ENV_FILE=.env.prod docker compose run --rm --no-deps transcript python scripts/init_transcript_models.py --directory /models
# Hugging Face连接不可用时，在上条命令最后加 --mirror；文件摘要校验相同。
```

3. 在生产环境文件加入 `TRANSCRIPT_ASR_ENABLED=true`，然后按现有流程运行 `migrate`、`api`、`admin`、`worker`、`transcript`。compose已为文案worker设置CPU=1、内存768MiB，模型卷持久化；API不会加载模型。不要扩容文案worker副本。
4. 抖音仍依赖管理端配置的有效会话，视频原始音轨用于识别，不能拿BGM音乐地址替代。B站无字幕时使用独立音轨，缺失时回退视频音轨。

## 本地开发

- Python依赖：`uv pip install -e '.[dev,postgres,cos,robot,asr]'`。
- 默认SenseVoice只需安装FFmpeg、Python ASR依赖及初始化模型。仅选择Whisper回退时，另需CMake和C++编译器，构建固定提交的whisper.cpp：

```bash
git clone https://github.com/ggml-org/whisper.cpp.git /tmp/bidong-whisper
cd /tmp/bidong-whisper
git checkout 4979e04f5dcaccb36057e059bbaed8a2f5288315
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF -DGGML_METAL=OFF
cmake --build build --target whisper-cli -j 1
```

- 回到server运行 `.venv/bin/python scripts/init_transcript_models.py`；配置 `.env` 中 `TRANSCRIPT_ASR_ENABLED=true`、`TRANSCRIPT_WHISPER_BIN`（绝对路径）、模型路径及FFmpeg路径；默认SenseVoice使用`TRANSCRIPT_SENSEVOICE_MODEL_PATH`和`TRANSCRIPT_SENSEVOICE_TOKENS_PATH`，Whisper路径仅回退时使用。
- `./dev.sh` 自动迁移并启动API、管理端、机器人及文案worker，Ctrl+C停止所有子进程。
- ASR未开通时，文案worker仍可提取平台已有字幕；无字幕任务明确提示服务尚未开放。

## 限制与运行维护

- 全局同时1个任务、最多等待10个任务，每用户1个未完成任务；任务会写数据库，离开页面不取消。
- ASR最长30分钟，输入媒体不超过256MiB；音轨下载最多5分钟、转码最多5分钟，识别流程总时间预算2小时。模型按需加载，子进程退出即释放模型内存。
- 任务心跳10秒、租约120秒；进程中断后恢复一次。两次中断后标记失败，用户可重试。正常处理成功、失败、无语音、超时均清临时文件；启动时清理超过任务上限的遗留目录。
- `docker compose logs -f transcript` 查看状态；`docker stats` 观察内存。文案只保存文字与真实起止时间，不保留音视频或签名媒体URL。
- 更换模型或语言配置时更新 `TRANSCRIPT_CACHE_VERSION`，避免复用旧配置的结果。
- 文案接口先校验卡片归属；读取和导出不会创建识别任务。没有活跃worker时提交返回503，平台原下载不受影响。

## 验收

- 先跑后端pytest、小程序Jest、迁移测试；对队列并发/重启和SQLite/PG分别验证。
- 真实ASR测试需调用实际FFmpeg、Silero、SenseVoice（或显式选择的Whisper）；静音/纯音测试确认无语音结果不进入Whisper。
- 中文口播样本验证分段、复制正文、TXT和SRT真实时间；识别存在错字属模型能力，不能将格式导出通过称作准确率通过。
- 用户提供抖音链接：`https://v.douyin.com/YFqZxeEjQtY/`。必须配置有效抖音会话后再测解析→排队→音轨→VAD→ASR→小程序查看/导出；会话未配时明确记录未完成，不能以模拟响应代替。
- Mac上的速度和内存不能代表云服务器，2核2GB生产机上线前还需测试接近30分钟的口播，并确认API、管理端响应及OOM情况。


## 2026-11-09 中文识别引擎升级

- 默认 `TRANSCRIPT_ENGINE=sensevoice`，使用固定版本的SenseVoice INT8中文CPU模型；模型文件约228MiB，词表同时初始化。识别子进程结束即释放模型。
- VAD也改为独立子进程，退出后才启动识别，避免两套ONNX运行时在worker中叠加占用内存。
- 仍保持1CPU/768MiB文案worker。SenseVoice每次最多读取12秒核心音轨及前后各1秒上下文；只保留核心区间内的CTC token，防止重复文字，跳过无语音区间。
- 字幕段开始时间取模型CTC时间戳，结束时间取下一token时间或音轨末尾，属于语音对齐估计；不使用固定2秒假时间。分块不影响时间轴绝对偏移。
- 初始化命令默认下载SenseVoice和VAD：`python scripts/init_transcript_models.py --directory /models`，连接受限时加`--mirror`。模型和词表均固定源提交并校验SHA256。
- 回退Whisper：运行初始化脚本加`--engine whisper`，设置`TRANSCRIPT_ENGINE=whisper`及原Whisper路径。不要让API与worker使用不同的引擎/语言/分块配置。
- 缓存键自动包含引擎、模型文件名、语言和分块设置。原base结果不会作为SenseVoice结果返回；同名模型替换时仍需更新`TRANSCRIPT_CACHE_VERSION`。
- 本地测试只比较同一段13秒视频，不代表总体准确率或生产机性能。仍可能出现同音字错误，建议上线前补充不同口音、背景音乐和较长口播样本。
