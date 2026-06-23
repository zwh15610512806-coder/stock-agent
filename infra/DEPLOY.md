# 云服务器公网部署

这个项目的公网部署方式是：一台云服务器运行 Docker Compose，`web` 容器对外提供页面，Nginx 将 `/api/` 代理到 `api` 容器。默认访问地址是 `http://服务器公网IP`。

## 1. 准备云服务器

推荐系统：Ubuntu 22.04/24.04 或 Debian 12。起步配置建议 2C/2G；如果 OCR 或 AI 报告使用频繁，建议 2C/4G。

云厂商安全组至少开放：

- `80/tcp`: 网站访问。
- `22/tcp`: SSH 管理，建议只允许你自己的 IP 访问。

初期不需要把你的电脑作为服务器。你的电脑只用于开发、打包或上传代码。

## 2. 安装 Docker

在云服务器上执行：

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

重新登录 SSH 后确认：

```bash
docker --version
docker compose version
```

## 3. 上传代码和环境变量

把项目上传到云服务器，例如：

```bash
scp -r ./股票 user@服务器公网IP:/opt/zhi-tou-terminal
```

也可以用 Git 拉取代码到 `/opt/zhi-tou-terminal`。

在服务器项目根目录创建 `.env`：

```bash
cd /opt/zhi-tou-terminal
cp .env.example .env
nano .env
```

只在服务器 `.env` 里填写密钥，不要提交 `.env`。AI/OCR 相关密钥不填时，对应功能会不可用或走 fallback，但网站和行情基础功能仍应可启动。

## 4. 启动公网服务

在服务器项目根目录执行：

```bash
docker compose -f infra/docker-compose.yml up -d --build
```

默认会把网站绑定到服务器 `80` 端口：

- 页面：`http://服务器公网IP`
- 健康检查：`http://服务器公网IP/healthz`

如果只想在本机临时验证，并且不想占用 `80` 端口，可改用：

```bash
WEB_PORT=8080 docker compose -f infra/docker-compose.yml up -d --build
```

然后访问 `http://127.0.0.1:8080`。

## 5. 运行维护

查看容器状态：

```bash
docker compose -f infra/docker-compose.yml ps
```

查看日志：

```bash
docker compose -f infra/docker-compose.yml logs -f
```

更新代码后重新部署：

```bash
docker compose -f infra/docker-compose.yml up -d --build
```

停止服务：

```bash
docker compose -f infra/docker-compose.yml down
```

## 6. 域名、HTTPS 和备案

当前配置先支持公网 IP 访问。后续如果绑定域名，建议再加 HTTPS。

如果域名解析到中国大陆服务器，通常需要在服务器接入商处完成 ICP 备案后才能正式对外提供网站服务。只用公网 IP 做技术验证时，可以先不处理域名和 HTTPS。
