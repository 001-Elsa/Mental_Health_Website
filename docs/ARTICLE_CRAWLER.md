# 心理文章采集

采集任务只保存文章标题、摘要、作者、来源、发布时间、封面地址和原文链接，不复制正文。默认来源包括可访问的知乎文章、中国大学生在线、阳光心理和高校心理中心公开页面。

```powershell
environment\venv\Scripts\python.exe -m scripts.crawl_psychology_articles
```

任务逐页限速请求，按 `source_url` 去重，单个来源失败不会中断整批任务。新增来源前应确认页面公开可访问，并遵守目标站点的服务条款与抓取规则。

Windows 公网部署脚本默认会在初始化数据库后运行一次采集；如果数据库已经存在，脚本会跳过会清库的演示数据 `seed.py`，只做表结构初始化和文章补库。需要强制重建演示数据时才传入 `-ReseedDemoData`。

```powershell
scripts\windows-deploy.ps1 -ProjectRoot C:\mental_health_website -Port 80
```
