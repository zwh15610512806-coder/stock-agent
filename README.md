# 智投终端

面向个人投研的公网可访问网站，覆盖 A股、港股、美股行情、大盘仪表盘、个股 K线、浏览器本地组合分析、腾讯云 OCR 持仓导入和 DeepSeek AI 研究报告。

## 结构

- `api/`: FastAPI 后端，负责免费延迟行情、组合计算、豆包视觉截图识别和 DeepSeek 报告。
- `web/`: Vite + React + TypeScript 前端，组合数据仅保存在浏览器本地。
- `infra/`: Docker 和 Nginx 部署配置。

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
npm run test
npm run dev
```

打开 `http://127.0.0.1:5173`。

## 环境变量

复制 `.env.example` 为 `.env`，填入需要的密钥。密钥只在后端使用，不能提交到版本库。

- `DEEPSEEK_API_KEY`: DeepSeek 报告生成密钥。
- `VOLCENGINE_API_KEY`: 火山方舟 API Key，用于豆包视觉模型识别券商持仓截图。
- `VOLCENGINE_API_BASE`: 默认 `https://ark.cn-beijing.volces.com/api/v3`。
- `VOLCENGINE_OCR_MODEL`: 默认 `doubao-seed-2-0-lite-260215`。
- `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`: 可选 fallback OCR 密钥。
- `MARKET_CACHE_TTL_SECONDS`: 后端行情缓存秒数。

## Docker

```powershell
docker compose -f infra/docker-compose.yml up --build
```

默认前端地址：`http://127.0.0.1`，后端通过同域 `/api/` 由 Nginx 代理，不直接暴露后端端口。

如果本机 `80` 端口已被占用，可指定本地端口：

```powershell
$env:WEB_PORT=8080
docker compose -f infra/docker-compose.yml up --build
```

然后打开 `http://127.0.0.1:8080`。

公网云服务器部署步骤见 [`infra/DEPLOY.md`](infra/DEPLOY.md)。

## 数据与合规边界

行情来自免费公开源或兜底演示数据，可能延迟、缺失或被缓存。AI 报告仅供研究参考，不构成任何证券买卖建议，不承诺收益，不应作为交易下单依据。

## 截图识别

`POST /api/ocr/positions` 默认使用火山方舟 OpenAI-compatible Chat Completions 接口，模型为 `doubao-seed-2-0-lite-260215`。后端会把截图转为 base64 图片输入，让模型返回结构化持仓 JSON，再标准化为本地组合持仓草稿。未配置 `VOLCENGINE_API_KEY` 或调用失败时，会尝试使用腾讯云 OCR fallback；两者都不可用时，接口会返回明确的失败提示。

## 免费行情源顺序

- A股/港股报价：优先 `AKShare` 东方财富接口；如果本机网络或远端限制导致失败，自动回退到腾讯免费延迟报价 `qt.gtimg.cn`；再失败才使用演示兜底数据。
- A股/港股 K线：优先 `AKShare` 历史行情；失败后回退到 Yahoo chart；再失败使用演示兜底数据。
- 美股报价/K线：优先 Yahoo chart 免费接口；如果遇到限流或网络失败，使用演示兜底数据。
- 组合分析：`POST /api/portfolio/analyze` 默认会用后端免费行情刷新现价；传入 `refresh_prices: false` 可只按本地录入现价计算。
- 后端请求第三方源时会尽量禁用本机代理环境，避免 `127.0.0.1:7890` 这类失效代理导致免费源不可用。
