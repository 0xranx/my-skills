---
name: douyin-cli
description: 抖音 CLI 工具。搜索视频、查看详情和评论、获取用户信息和作品列表。当用户提到抖音、Douyin、短视频搜索时使用此 Skill。
---

# 抖音 CLI

通过 Playwright 浏览器自动化实现抖音 Web API 调用，无需官方 API Key。

## 前置条件

1. 安装依赖：`pip install -r requirements.txt && playwright install chromium`
2. 首次使用需登录：`python douyin.py login`（会打开浏览器，手机扫码）

验证登录状态：
```bash
python skills/douyin-cli/douyin.py status
```

## 触发条件

以下情况使用此 Skill：
- 用户要搜索抖音内容
- 用户要查看某个抖音视频的详情或评论
- 用户要了解某个抖音创作者的主页和作品
- 用户发送了 douyin.com 链接

## 搜索

```bash
python skills/douyin-cli/douyin.py search "关键词"          # 搜索视频
python skills/douyin-cli/douyin.py search "关键词" --user    # 搜索用户
```

## 视频详情和评论

```bash
python skills/douyin-cli/douyin.py detail <aweme_id>         # 视频详情
python skills/douyin-cli/douyin.py comments <aweme_id>       # 评论列表
python skills/douyin-cli/douyin.py video <aweme_id>          # 详情 + 评论
```

aweme_id 从搜索结果或视频 URL 中获取（`/video/` 后面的数字）。

## 用户信息

```bash
python skills/douyin-cli/douyin.py user <sec_user_id>        # 用户主页
python skills/douyin-cli/douyin.py posts <sec_user_id>       # 用户作品列表
```

sec_user_id 从用户主页 URL 中获取（`/user/` 后面的字符串）。

## 典型工作流

### 「帮我搜一下抖音上关于 XX 的视频」
1. `search "XX"` 搜索
2. 对感兴趣的视频 `video <id>` 查看详情+评论
3. 总结返回

### 「帮我看看这个抖音博主」
1. `user <sec_user_id>` 获取主页
2. `posts <sec_user_id>` 查看作品列表

### 「看看这个视频的评论区」
1. `comments <aweme_id>` 获取评论
2. 分析评论区反馈

## 注意事项

- 首次使用必须登录，Cookie 保存在 `data/douyin_cookie.txt`
- 登录后使用 headless 模式（不弹窗）
- 也可手动粘贴 Cookie：`python douyin.py set-cookie "..."`
- 抖音有反爬机制，高频请求可能触发验证码
- 评论需要页面滚动触发加载，首次可能获取不全
