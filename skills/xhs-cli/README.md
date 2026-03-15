# xhs-cli

小红书 CLI 工具 — 通过 Playwright 浏览器自动化调用小红书 Web API，无需官方 API Key。

## 功能

- **搜索**：按关键词搜索笔记，支持排序和类型过滤
- **详情**：获取笔记详情、评论列表、用户主页
- **统计**：查看自己账号所有帖子的互动数据
- **发布**：自动化发布图文笔记到创作者中心

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 2. 登录（浏览器扫码）
python xhs.py login

# 3. 验证
python xhs.py me
```

## 命令一览

```bash
python xhs.py search "关键词"                    # 搜索
python xhs.py detail <note_id> <xsec_token>     # 笔记详情
python xhs.py comments <note_id> <xsec_token>   # 评论
python xhs.py note <note_id> <xsec_token>       # 详情+评论
python xhs.py user <user_id>                     # 用户主页
python xhs.py me                                 # 当前用户
python xhs.py unread                             # 未读通知
python xhs.py stats [--detail]                   # 账号数据

python xhs_publish.py login                      # 创作者中心登录
python xhs_publish.py publish --draft x.md --images a.jpg b.jpg
```

## 配置

编辑 `config.yaml` 或设置环境变量：

```bash
export XHS_ACCOUNT_NAME="你的昵称"        # stats 命令过滤用
export XHS_SEARCH_KEYWORD="搜索关键词"    # stats 命令搜索用
```

## 作为 AI Skill

将 `skills/xhs-cli/` 放到项目中，AI 代理通过 `SKILL.md` 自动识别。支持 Claude Code、Cursor 等。

## 已知限制

- 依赖 Playwright 浏览器（首次安装约 200MB）
- 需要手动扫码登录，Cookie 有效期约 30 天
- 高频请求可能触发验证码
- `xsec_token` 有时效性，过期需重新搜索获取
