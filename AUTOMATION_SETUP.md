# 自动刷新配置

## 已实现

- GitHub Actions 每天 `03:00 UTC` 运行，即北京时间 `11:00`。
- Actions 下载三个 Google Sheet CSV，重新生成 `index.html` 并推送到 `main`。
- Cloudflare Pages 的 `/refresh-data` Function 可由看板“立即更新”按钮触发同一工作流。

## 启用线上“立即更新”

1. 在 GitHub 创建 Fine-grained personal access token。
2. Resource owner 选择 `rishisann1999-coder`。
3. Repository access 只选择 `PH-shopee-dashboard`。
4. Repository permissions 将 `Actions` 设置为 `Read and write`。
5. 在 Cloudflare Pages 项目打开 `Settings` → `Variables and Secrets`。
6. 为 Production 添加加密变量 `GITHUB_ACTIONS_TOKEN`，值为上一步的 Token。
7. 再添加加密变量 `REFRESH_KEY`，值为自定义刷新口令。
8. 重新部署当前项目。

Token 仅保存在 Cloudflare 服务端，不会进入浏览器或 HTML。
点击看板“立即更新”时输入 `REFRESH_KEY`；同一浏览器会话只需输入一次。

如果 GitHub Actions 的提交步骤提示无写入权限，请进入仓库 `Settings` → `Actions` → `General`，将 `Workflow permissions` 设置为 `Read and write permissions`。

## 手动备用入口

也可以进入 GitHub 仓库的 `Actions` → `Refresh dashboard data` → `Run workflow` 手动运行。
