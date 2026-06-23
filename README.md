# 息壤投研

面向个人投研的本地优先网站，覆盖市场仪表盘、宏观面板、A 股选股、ETF 观察、个股检索、持仓组合分析、OCR 持仓导入和 AI 研究报告。

## 项目结构

- `api/`: FastAPI 后端，负责免费行情源、宏观数据、A 股选股器、ETF、组合计算、OCR 和 DeepSeek 报告。
- `web/`: Vite + React + TypeScript 前端，持仓数据只保存在浏览器本地。
- `infra/`: Docker Compose、Nginx 和部署配置。

## 本地开发

后端：

```powershell
cd api
uv run pytest -q
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd web
npm install
npm test
npm run dev
```

打开 `http://127.0.0.1:5173`。前端默认访问同域 `/api`，本地联调可在 `web/.env.local` 或环境变量里设置 `VITE_API_BASE=http://127.0.0.1:8000`。

## 环境变量

复制 `.env.example` 为 `.env`，只在本地或服务器填写密钥，不要提交 `.env`。

- `DEEPSEEK_API_KEY`: DeepSeek Chat Completions 报告生成密钥。
- `DEEPSEEK_API_BASE`: 默认 `https://api.deepseek.com`。
- `DEEPSEEK_MODEL`: 默认 `deepseek-chat`。
- `VOLCENGINE_API_KEY`: 火山方舟 API Key，用于豆包视觉模型识别持仓截图。
- `VOLCENGINE_API_BASE`: 默认 `https://ark.cn-beijing.volces.com/api/v3`。
- `VOLCENGINE_OCR_MODEL`: 默认 `doubao-seed-2-0-lite-260215`。
- `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`: 可选腾讯云 OCR fallback 密钥。
- `TENCENTCLOUD_REGION`: 默认 `ap-guangzhou`。
- `TENCENTCLOUD_OCR_ENDPOINT`: 默认 `ocr.tencentcloudapi.com`。
- `MARKET_CACHE_TTL_SECONDS`: 后端行情与仪表盘缓存秒数。
- `VITE_API_BASE`: 可选前端本地开发 API 地址，Docker 同域部署时保持空值。

## 数据源

当前策略是“免费优先 + A 股优先”，不接券商自动登录或同步。

- 市场页：A 股成交额优先使用 AKShare `stock_sse_summary` + `stock_szse_summary` 的交易所总貌口径；指数报价复用腾讯免费行情、AKShare 和 Yahoo Chart。
- 宏观页：`/api/macro/dashboard` 使用 AKShare 的 LPR、CPI、GDP、PMI、新增人民币贷款、中美国债收益率和 BOC 汇率。
- 选股页：`/api/stocks/screener` 使用 AKShare `stock_zh_a_spot_em` 做 A 股筛选；`/api/symbols/search` 保留静态核心清单并扩展 A 股完整股票池缓存。
- ETF 页：`/api/etfs/search` 和 `/api/etfs/candles` 使用 AKShare `fund_etf_spot_em`、`fund_etf_hist_em`。
- 持仓页：持仓仍来自本地 CSV、OCR 或手动录入；组合分析可尝试刷新真实行情，失败时保留用户录入现价并返回 `quote_status` / `data_warnings`。
- 数据源状态：`/api/sources/status` 只检查配置和缓存目录状态，不主动访问第三方网络。

后端使用 `.runtime/*.sqlite3` 做快照缓存。免费源不可用时，市场/宏观/选股器/ETF 返回空数组、`null` 或明确 `unavailable/stale` 状态，不把模拟数据伪装成真实数据。

## API 摘要

- `GET /api/market/dashboard`
- `GET /api/macro/dashboard`
- `GET /api/symbols/search`
- `GET /api/stocks/screener`
- `GET /api/etfs/search`
- `GET /api/etfs/candles`
- `POST /api/portfolio/analyze`
- `POST /api/ocr/positions`
- `POST /api/ai/portfolio-report`
- `GET /api/sources/status`

## Docker

```powershell
docker compose -f infra/docker-compose.yml up --build
```

默认前端地址是 `http://127.0.0.1`，后端通过 Nginx 同域 `/api/` 代理，不直接暴露后端端口。若本机 `80` 端口被占用：

```powershell
$env:WEB_PORT=8080
docker compose -f infra/docker-compose.yml up --build
```

然后打开 `http://127.0.0.1:8080`。

Compose 会把 API 容器的 `/app/.runtime` 挂载为 `api-runtime` volume，用于保留 SQLite 快照缓存，并通过 `/healthz` 做健康检查。

公网云服务器部署步骤见 [`infra/DEPLOY.md`](infra/DEPLOY.md)。

## 测试

```powershell
cd api
uv run pytest -q

cd ../web
npm test
npm run build
```

## 合规边界

所有行情、宏观、ETF 和选股数据都来自免费公开源，可能延迟、缺失、限流或被缓存。AI 报告仅供研究参考，不构成证券买卖建议，不承诺收益，不应作为交易下单依据。
