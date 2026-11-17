# ECS 自动测试与部署

适用于当前单台 Ubuntu ECS、systemd、Nginx 和本地 SQLite 部署。工作流见 `.github/workflows/ecs.yml`。

## 日常使用

提交或合并代码到 `master` 后，GitHub Actions 会并行执行后端测试、部署脚本测试和前端生产构建。全部通过后，将该提交的后端源码及前端 standalone 产物部署到现有 ECS。PR 只测试，不部署。

在 GitHub 仓库的 **Actions → Test and deploy ECS** 查看运行结果。需要重新执行时，点击 **Run workflow**，选择 `master`。同一个已成功部署的提交会跳过；失败的提交可以重试。手动选择其他分支只会执行测试和构建。

部署按顺序执行；准备上线时会检查 master 是否已有更新，过期提交跳过部署。正在部署时不要取消任务，特别是执行数据库迁移期间。

## 首次配置

1. 服务器保留现有 `/etc/horizon/horizon.env`、`web.env`、数据库 `/var/lib/horizon/horizon.db` 及 Nginx 配置。模型凭据继续只放在服务器配置文件里。
2. 将本目录的 `ecs_release.py`、`install-ci-receiver.sh` 放到服务器同一目录，在该目录以 root 执行 `bash install-ci-receiver.sh`。安装器适配现有 `/opt/policy-espresso/current` 布局，创建 `horizon-deploy` 用户和固定命令入口，更新 systemd 启动配置。安装时不会重启正在运行的服务。
3. 为 Actions 单独生成 Ed25519 密钥。将公钥添加到 `/home/horizon-deploy/.ssh/authorized_keys`，每行使用下面的限制前缀。文件权限为 600，所属用户为 `horizon-deploy`。

   ```text
   restrict,command="/usr/local/bin/horizon-ci-dispatch" ssh-ed25519 <公钥内容> horizon-github-actions
   ```

4. 在仓库 **Settings → Secrets and variables → Actions → New repository secret** 中添加以下三项。需要有管理 Actions Secrets 的权限。

   | 名称 | 内容 |
   | --- | --- |
   | `ECS_HOST` | ECS 公网 IP，不带协议和路径 |
   | `ECS_DEPLOY_KEY` | 上一步生成的完整专用私钥 |
   | `ECS_KNOWN_HOSTS` | 已通过可信连接核验的 SSH 主机公钥记录，格式为 `IP key-type base64-key` |

   不要将 root 密码、模型 API Key 写进工作流或提交到仓库。SSH 入口必须能从 GitHub 托管 runner 访问。

5. 将工作流提交到 master，检查首次 Actions 运行的 `backend`、`frontend`、`deploy` 三个任务。部署后查看 `deploy` 日志中的提交 SHA，并通过公网地址检查页面。

## 部署与恢复

服务端先校验归档摘要、路径和提交号，然后在 `/opt/policy-espresso/releases/<SHA>/horizon` 解包，并以应用用户建立该版本独立的 Python 环境。前端直接使用 CI 构建的 standalone 产物。依赖安装期间旧版本继续服务。

准备完成后，停止前后端服务，将 SQLite 备份到 `/var/backups/horizon/before-*.sqlite3`，执行 Alembic 迁移，切换 `current` 链接并启动服务。API 数据库检查和前端登录页面通过后，将成功提交写入 `/opt/policy-espresso/deployed.json`。

迁移、启动或健康检查失败时，脚本停止新服务、恢复旧代码链接及本次数据库备份，再启动旧版本，Actions 显示失败。数据库恢复针对当前固定路径的 SQLite；不适用于 RDS/OSS 或多台 ECS。部署窗口会有短暂停机。

失败时先查看 Actions 日志，再在服务器执行：

```bash
systemctl status horizon-api horizon-web --no-pager
journalctl -u horizon-api -u horizon-web -n 100 --no-pager
cat /opt/policy-espresso/deployed.json
```

专用 SSH 密钥只接受 `status` 和 `deploy <完整SHA> <归档SHA256>`，不能执行任意 shell。接收器和 systemd 配置由 root 管理，普通业务提交不更新这些配置；若修改部署接收器，必须由维护者重新安装。旧版本目录和上线前数据库快照暂时保留，需要维护者定期检查磁盘占用。
