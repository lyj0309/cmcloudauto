# cmcloudauto

在 Wine 中运行 `Ecloud Cloud Computer Application.exe`，使用 KasmVNC 提供浏览器桌面，并可从只读 secret 自动登录、连接云电脑。

## 启动

默认读取现有压缩包：

```text
/home/sun/tdx-docker/CloudComputer.zip
```

初始化浏览器密码和登录 secret：

```bash
cd /home/sun/cmcloudauto
cp .env.example .env
printf '%s' '你的账号' > secrets/username
printf '%s' '你的密码' > secrets/password
chmod 600 secrets/username secrets/password
docker compose up -d --build
```

浏览器打开 `http://127.0.0.1:3040`。KasmVNC 用户名默认是 `cmcloud`，密码取 `.env` 的 `KASMVNC_PASSWORD`。

Wine 客户端默认运行在 `1180x540` 的普通窗口中，避免 Qt 会话客户端全屏后抢占 VNC 鼠标。可通过 `.env` 的 `CMCLOUD_DESKTOP_SIZE` 调整尺寸。

首次启动会把约 1.9 GiB 的客户端解压到 `./config/cmcloud-app`，同时初始化 `./config/wineprefix`；后续重启不重复解压。运行状态、客户端缓存和 Wine 前缀均持久化在 `./config`。

Wine prefix 在首次启动时写入 `./config`，不预置进镜像。应用层现在直接继承公开的 `ghcr.io/lyj0309/docker-wine-vnc:latest`，不再在本项目重复构建 KasmVNC/Wine 基础层；本项目镜像只增加自动登录脚本和运行时配置。首次构建会拉取基础镜像，后续只在应用层有变化时重新构建。

也可以先显式拉取基础镜像：

```bash
docker pull ghcr.io/lyj0309/docker-wine-vnc:latest
docker compose build
```

## 自动登录

顶层应用是 Electron，不是 Qt；连接云桌面后启动的 `drivers/H3C/Ecloud Cloud Computer Session.exe` 才是 Qt 会话程序。自动登录器通过 Electron 的本机 DevTools 端口填写已验证的登录控件：

```text
input.inputName
input.inputPwd
button.input31
```

账号密码仅从 `/run/secrets/username` 和 `/run/secrets/password` 读取，不写入镜像或日志。删除/清空任一 secret，或在 `.env` 设置 `CMCLOUD_AUTO_LOGIN=0`，即可关闭自动登录。

登录成功后脚本会点击设备列表中的可见“进入”控件；存在多个云电脑时，在 `.env` 设置 `CMCLOUD_MACHINE_NAME=设备显示名称` 可指定设备，否则采用第一个可见控件。设置 `CMCLOUD_AUTO_CONNECT=0` 可只登录不连接。点击动作完成即视为自动化成功，后续 Windows 云桌面会话是否真正建立不作为脚本成功条件。

Wine 子进程默认使用 `UTC`。这是为了避免 CMSS Qt 会话组件在 Wine 下把本地时区重复计入时间戳、进而以 `login timestamp is invalid` 拒绝连接；Kasm 桌面和容器日志仍使用 `TZ` 指定的时区。

首次运行时脚本会勾选隐私协议，并处理客户端的“我已阅读并同意”提示框；验证码、短信验证、设备确认或二次认证仍需要在浏览器桌面中人工完成。客户端自己的“记住密码/自动登录”选项不会被脚本打开。

## 排查

```bash
docker compose ps
docker compose logs -f cmcloud
tail -f config/logs/cmcloud-wine.log
tail -f config/logs/autologin.log
docker compose exec --user abc cmcloud /usr/local/bin/launch-cmcloud.sh
```

注意：登录主界面能在 Wine 中启动，并不等于 Windows 云桌面会话一定可连接。H3C/CMSS 组件带 Windows 服务、驱动、USB/磁盘重定向和提权工具；Wine 不支持的内核驱动能力会被禁用，实际连接结果需要以运行测试为准。
