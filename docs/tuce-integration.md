# tuce.asia 接入准备

目前仅完成本地接入文件与部署模板，未改动 tuce.asia，未创建 DNS 记录或部署服务器。

## 1. 本地看按钮

启动服务后访问 http://127.0.0.1:8000/integration-preview.html 。右下角按钮进入本地测评页；不自动调用 AI、不读取官网表单、不发送通知。实际官网样式兼容性尚需拿到官网源码后验证。

## 2. 官网添加一行代码

下面使用 `ai.tuce.asia` 作为规划示例，**该地址并未配置或验证**。上线前替换为实际已部署的 HTTPS 地址，将这行放进官网公共布局的 `</body>` 前：

```html
<script defer src="https://ai.tuce.asia/tuce-widget.js" data-url="https://ai.tuce.asia/"></script>
```

按钮采用隔离样式，不引入框架，默认右下角距底部 88px，以避让底部咨询条；具体避让距离仍需与官网联调。点击同页跳转到测评站。不是 iframe：测评站部署模板禁止被嵌套，管理后台不在官网导航中显示。若官网设置 CSP，需要允许实际测评站域名的脚本以及该控件的内联样式；不要为此随意放宽整站安全策略，可以改成官网原生链接按钮。

## 3. 部署前需提供

- 官网源码位置/仓库，以及现有托管方式。
- 一台可运行 Docker Compose、可持久保存数据的服务器；或现有 Python 服务环境。
- 可管理的 DNS，把实际测评子域名解析到服务器。
- DeepSeek Key、管理口令、通知配置只放服务端环境变量；不要放官网脚本或 Git。

## 4. Docker Compose + Caddy 模板

如果服务器已有 Nginx/Caddy 占用 80/443，应由现有反向代理接入，**不要直接启动本模板的 Caddy 抢占端口**。以下适用于空闲的专用服务器：

1. 将仓库源码放到服务器，复制 `agent/.env.example` 为 `agent/.env`，设权限 600。
2. 填入有效 `DEEPSEEK_API_KEY`、至少 32 字符随机 `ADMIN_TOKEN`、实际 `EVALUATION_DOMAIN`。通知按需填写。域名值不要带协议和路径。
3. 先配置 DNS 和服务器防火墙：开放 80/443；不开放 8000。
4. 在项目根目录执行：

```bash
docker compose --env-file agent/.env -f deploy/compose.yaml config --quiet
docker compose --env-file agent/.env -f deploy/compose.yaml up -d --build
```

Caddy 为正确指向服务器的域名申请 HTTPS。应用以非 root 用户运行；SQLite 在 `leads` 命名卷中，重建容器保留数据。**不要运行 `down -v`，它会删除数据卷。** 构建上下文排除本地密钥、数据库、虚拟环境；本机现有数据库不会自动上传。

模板未在真实 Docker/服务器环境验收。当前依赖与镜像未锁定摘要，正式发布前应固定经过验证的版本。健康检查不验证 AI Key 或通知送达。

## 5. 数据库迁移和备份

本机数据库仍是 `data/leads.db`。本机生成一致性备份：

```bash
python3 scripts/backup_db.py --output-dir backups
```

备份包含手机号等个人信息，权限为仅拥有者可读写，不应放入静态目录或提交 Git。应放在加密存储中，并按业务要求设置保留/清理策略。

备份容器数据库（从项目根目录执行）：

```bash
mkdir -p backups
chmod 700 backups
docker compose --env-file agent/.env -f deploy/compose.yaml exec -T app python - --source /app/data/leads.db --output-dir /tmp < scripts/backup_db.py
```

上面的命令在容器 `/tmp` 生成备份且打印确切路径；使用 `docker compose ... cp app:/tmp/<打印的文件名> backups/` 取出，再将宿主机文件权限设为 600。容器临时目录不应作为长期备份位置。按服务器实际环境配置定时任务与异地备份，此项目不自动创建系统定时任务。

如果需要迁移本机已有数据：先生成一致性快照，再停应用、导入到部署卷并核对权限。不要在运行中覆盖数据库，也不要把测试/真实线索未经确认混入新站。

## 6. 已做与仍需验收

已做：
- 未配置管理口令时拒绝读取线索；AI 连通性测试也要求管理口令。
- 测评预览不再返回理由；成功留资后由服务端返回完整报告。
- API 响应禁止缓存，跨域 API 默认不开放，模型失败不向客户端显示底层错误。
- 前端重新测评时重置解锁状态。

仍需正式发布前处理：
- AI 费用硬上限与多实例共享限流。当前已有单进程按来源限流和请求体大小限制，但不等同于预算封顶。
- 联系方式真实性验证、重复提交与通知重试机制。
- 选校质量复核（GPA 计分制与语言成绩校验已补齐）。
- 隐私政策正文、授权记录、线索保存/删除规则。
- 真实 AI 调用、通知送达、手机端官网联调和备份恢复演练。

留资后返回报告不代表验证了手机号或微信真实性，仍需后续反滥用措施。后台口令不是多用户账号系统。上线前还应控制管理入口访问范围。

配置参考：[Caddy 反向代理](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)、[请求体大小限制](https://caddyserver.com/docs/caddyfile/directives/request_body)、[Compose 必填变量](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)。

## 本次本地验证

- 自动化测试 11 项通过；AI 与通知均替换为测试实现，不调用外部服务。
- 三份前端脚本语法检查通过，按钮可进入测评页。
- Compose 配置校验通过；Docker daemon 未运行，未构建镜像或验证容器启动。
- 备份脚本通过临时数据库内容与文件权限验证，未复制真实线索。
- 本地 `agent/.env` 已补充随机 `ADMIN_TOKEN`（已有口令则保留），重启服务后登录后台时使用此值。请勿将该文件或口令提交到 Git、复制进官网脚本。


## 2026-09-01 当前项目微调

不接入任何资料库、不合并旧项目，不新增运行依赖。

- 明确 4 分制、5 分制、百分制；录入、通知、后台与导出保留满分。
- 增加其他国家/地区填写及语言类型/总分联合校验；支持托福两种制式。
- 新增等待提示；移除未经确认的 24 小时联系承诺和保证录取措辞。
- 验证 AI 结果非空、无重复院校；推荐仍为未经实时核验的初步建议。
- 本地回归测试扩展至 33 项，通过；不调用真实 AI、不发送通知。

## 2026-09-01 防刷进度

- 测评与留资接口新增单进程内按客户端来源限流，默认窗口 600 秒，分别允许 10 次和 20 次。
- 超限返回 HTTP 429、中文提示和 `Retry-After`；超限测评不会继续调用 AI。
- 定期清理过期来源记录，避免限流字典随长期运行无限增长。
- Docker 部署只信任默认 Docker 私网段的代理头，Caddy 后的真实来源地址可用于限流；应用端口仍不直接暴露公网。
- 回归测试扩展至 37 项并通过。该方案适合当前单进程部署；多进程或多实例需使用 Redis 或网关共享状态。
