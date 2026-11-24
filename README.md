# 食尽其用

本地运行的家庭食材管理与智能菜谱推荐系统。支持库存批次和临期提醒、食材字典与菜谱、五维推荐、采购清单、浪费登记与统计、偏好和 CSV 导入导出。

## 本地启动

项目使用 Python 3.11 或 3.12、PostgreSQL 15 或以上版本和 Node.js 20。先在本地 PostgreSQL 中创建 UTF-8 数据库 `shijinqiyong`，并准备有建表权限的数据库账号。

1. 在项目根目录创建虚拟环境并安装后端依赖。首次配置可从 `.env.example` 复制出本地 `.env`。

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
   if (!(Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
   ```

   在 `.env` 填写本地的 `DATABASE_URL` 和随机生成的 `SECRET_KEY`。数据库口令中的 URL 特殊字符需编码。环境文件由 Git 忽略。

2. 在项目根目录建表并启动 Flask。需要预置食材和菜谱时可执行 `seed-demo`。

   ```powershell
   .\.venv\Scripts\python.exe -m flask --app backend:create_app init-db
   .\.venv\Scripts\python.exe -m flask --app backend:create_app seed-demo
   .\.venv\Scripts\python.exe -m backend.app
   ```

3. 在另一个 PowerShell 终端进入项目的 `frontend` 目录并启动 Vue。

   ```powershell
   Set-Location frontend
   npm.cmd ci
   npm.cmd run dev
   ```

4. 打开 [食尽其用](http://localhost:5173) 并注册账户。Vite 将浏览器的 `/api` 请求转发给 `http://127.0.0.1:5000`。

## 推荐和 DeepSeek

推荐先按忌口和耗时过滤，再以临期利用、库存覆盖、口味、耗时和每份营养评分。默认使用详细设计中的 3 天临期阈值和 0.35、0.30、0.15、0.10、0.10 权重。数量按质量、体积和各计数单位计算，生成采购清单时合并需求后统一抵扣库存。

点击推荐卡片上的「DeepSeek 解读」时，Flask 将菜谱摘要、推荐理由和采购缺口发送给 DeepSeek。配置项为根目录 `.env` 的 `DEEPSEEK_API_KEY` 和 `DEEPSEEK_MODEL`，默认模型为 `deepseek-flash`。配置缺失或请求失败时显示本地解读。参考 [DeepSeek API 文档](https://api-docs.deepseek.com/)。

## 验证

后端测试覆盖认证、用户隔离、五维评分、缺口舍入、浪费扣减、CSV 原子导入和 DeepSeek 回退。设置 `TEST_DATABASE_URL` 可在 PostgreSQL 上验证行锁和事务，每个用例会创建并清理独立的测试 schema。缺省使用 SQLite 运行其余回归用例。

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q backend/tests
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
```

从脚本直接调用写入 API 时，使用 `http://localhost:5173` 来源的 `Origin` 或 `Referer`，并在登录后携带会话 Cookie。请求日志位于 `.local/logs/app.log`。
