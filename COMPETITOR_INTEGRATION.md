# 竞品监控接入

在现有导航最右侧新增“竞品监控”。内部保留菲律宾竞品看板的五个区块、22个月完整历史及一级至四级类目；默认显示 Skintific 自身。月度数据及更新时间独立显示，不沿用经营看板的日度查询日期。切回原模块时恢复原筛选和刷新入口。

模块以同站点 `assets/competitor/index.html` 隔离加载，仅首次点击竞品页签时请求竞品数据。压缩后的列字典及22个月份文件由浏览器无损还原，全部108,326条记录、店铺／商品ID、网页排名补充及缺失状态保持不变。当前月度文件最大不足1 MB，符合 Cloudflare Pages 单文件25 MiB限制。加载失败显示重试提示；iframe只接受同源且来源窗口匹配的状态消息。

竞品模块使用视口内的固定框架：主标题、导航、数据说明、类目与月份筛选及五个页签保持不动，仅其下方分析区域独立滚动。切换内部页签或上方筛选时，分析区域回到顶部。标题与说明文字、筛选及分析卡片采用紧凑间距；切换原经营模块后恢复其常规页面滚动。嵌入样式独立放在 `assets/competitor-embed.css`，不影响“独立打开”的页面。样式与脚本版本随资源内容变化，避免旧缓存延用之前的滚动布局。

`inject_competitor_page.py` 已接入 `build_flagship_onsite_page1.py`，日常重建会保留该入口。部署脚本原本已复制整个 `assets` 目录，无需变更 Cloudflare 设置。`assets/competitor-shell.*`、`competitor-loader.js` 和 `competitor-bridge.js` 为接入代码；原竞品功能文件由打包命令从已核验看板复制。

## 更新竞品快照

先完成本机 Brand Portal 月度采集、网页名次复核并发布本机竞品看板，再运行：

```powershell
& '../market-intelligence/.venv/Scripts/python.exe' -X utf8 scripts/package_competitor.py --source '../market-intelligence/public'
& '../market-intelligence/.venv/Scripts/python.exe' -X utf8 inject_competitor_page.py
& '../market-intelligence/.venv/Scripts/python.exe' -X utf8 tests/verify_competitor_integration.py --source-data '../market-intelligence/public/data.js'
```

打包程序仅读取 `public` 中明确列出的网页文件，不复制登录配置、Cookie、源导出或数据库。每个月份文件带内容哈希；`manifest.json` 最后发布并关联同一版快照。确认数据及预览后，再将 `assets` 与相关接入代码提交、部署。

现有经营数据每日刷新仅重建主看板，不会重新采集或更新竞品快照。竞品每月2号的本机采集与线上发布是两个步骤；当前未新增从本机向 GitHub 自动发布的任务。

## 发布与回归检查

运行 `scripts/preview_competitor.py` 后，可通过 `http://127.0.0.1:8767/#competitor` 检查本地效果。确认后将接入代码及公开资源提交到 `main`，现有 `Deploy dashboard to Cloudflare Pages` 工作流会发布到原站点。发布后检查 `/#competitor`、五个内部页签、四级类目筛选及切回原模块。

“重新加载”会重新请求完整的竞品页面，恢复默认自身视图；普通模块切换保留已加载页面及其筛选状态。
