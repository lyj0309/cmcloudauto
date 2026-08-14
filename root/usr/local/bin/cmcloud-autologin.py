#!/usr/bin/python3
"""Fill Ecloud's Electron login form through its loopback DevTools endpoint."""

import itertools
import json
import os
import pathlib
import time
import urllib.request

import websocket


def log(message: str) -> None:
    print(f"[cmcloud-autologin] {message}", flush=True)


def read_secret(env_name: str, default_path: str) -> str:
    path = pathlib.Path(os.environ.get(env_name, default_path))
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def list_targets(port: int) -> list[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2) as response:
        return json.load(response)


def send_command(ws: websocket.WebSocket, request_ids, method: str, params: dict) -> dict:
    request_id = next(request_ids)
    ws.send(json.dumps({
        "id": request_id,
        "method": method,
        "params": params,
    }))
    while True:
        message = json.loads(ws.recv())
        if message.get("id") == request_id:
            return message


def evaluate(ws: websocket.WebSocket, request_ids, expression: str) -> dict:
    return send_command(ws, request_ids, "Runtime.evaluate", {
        "expression": expression,
        "returnByValue": True,
        "awaitPromise": True,
    })


def evaluate_target(target: dict, port: int, expression: str) -> dict:
    ws = websocket.create_connection(
        target["webSocketDebuggerUrl"],
        timeout=10,
        origin=f"http://127.0.0.1:{port}",
    )
    try:
        response = evaluate(ws, itertools.count(1), expression)
        return response.get("result", {}).get("result", {}).get("value", {})
    finally:
        ws.close()


def fill_credentials_target(target: dict, port: int, username: str, password: str) -> bool:
    ws = websocket.create_connection(
        target["webSocketDebuggerUrl"],
        timeout=10,
        origin=f"http://127.0.0.1:{port}",
    )
    request_ids = itertools.count(1)
    try:
        for selector, value in (
            (".inputName input", username),
            (".inputPwd input, input[type=password]", password),
        ):
            expression = f"""
              (() => {{
                const input = document.querySelector({json.dumps(selector)});
                if (!input) return false;
                input.focus();
                input.select();
                return true;
              }})()
            """
            response = evaluate(ws, request_ids, expression)
            ready = response.get("result", {}).get("result", {}).get("value", False)
            if not ready:
                return False
            send_command(ws, request_ids, "Input.insertText", {"text": value})
        return True
    finally:
        ws.close()


def main() -> int:
    username = read_secret("CMCLOUD_USERNAME_FILE", "/run/secrets/username")
    password = read_secret("CMCLOUD_PASSWORD_FILE", "/run/secrets/password")
    if not username or not password:
        log("username/password secret is absent or empty; leaving the login window untouched")
        return 0

    port = int(os.environ.get("CMCLOUD_DEBUG_PORT", "9222"))
    timeout = int(os.environ.get("CMCLOUD_LOGIN_TIMEOUT", "180"))
    deadline = time.monotonic() + timeout
    target = None
    already_logged_in = False
    connected_page_probe = "Boolean(document.querySelector('.enterImg.active, .desktop-item .card-item'))"

    fill_expression = f"""
      (() => {{
        const visible = element => element.getBoundingClientRect().width > 0;
        const consent = [...document.querySelectorAll('button.sureBtn')]
          .find(element => visible(element) && element.textContent.trim() === '我已阅读并同意');
        if (consent) {{
          consent.click();
          return {{ok: false, consented: true, url: location.href}};
        }}
        const privacyText = [...document.querySelectorAll('.rp1')]
          .find(element => visible(element) && element.textContent.includes('隐私政策'));
        const privacy = privacyText?.parentElement?.querySelector('button');
        if (privacy && !privacy.classList.contains('fp')) {{
          privacy.click();
          return {{ok: false, acceptedPolicy: true, url: location.href}};
        }}
        const username = document.querySelector('input.inputName, .inputName input');
        const password = document.querySelector('input.inputPwd, .inputPwd input, input[type=password]');
        if (!username || !password) {{
          const passwordMode = [...document.querySelectorAll('button.password img')].find(visible);
          if (passwordMode) passwordMode.click();
          return {{ok: false, switchedMode: Boolean(passwordMode), url: location.href}};
        }}
        return {{ok: true, url: location.href}};
      }})()
    """

    while time.monotonic() < deadline:
        try:
            for candidate in list_targets(port):
                if candidate.get("type") != "page" or not candidate.get("webSocketDebuggerUrl"):
                    continue
                if evaluate_target(candidate, port, fill_expression).get("ok"):
                    target = candidate
                    break
                if evaluate_target(candidate, port, connected_page_probe):
                    already_logged_in = True
                    break
            if target or already_logged_in:
                break
        except (OSError, ValueError, websocket.WebSocketException):
            pass
        time.sleep(2)

    if not target and not already_logged_in:
        log(f"account login form was not ready within {timeout}s")
        return 1

    if target:
        click_expression = """
          (() => {
            const button = document.querySelector('button.input31, .input31');
            if (!button) return {ok: false, reason: 'login-button-not-found'};
            if (button.disabled) return {ok: false, reason: 'login-button-disabled'};
            button.click();
            return {ok: true};
          })()
        """
        login_result_expression = """
          (() => ({
            loggedIn: Boolean(document.querySelector('.enterImg.active, .desktop-item .card-item')),
            rejected: document.body.innerText.includes('用户名密码错误'),
            stillLogin: Boolean(document.querySelector('button.input31, .input31')),
          }))()
        """
        # The first secure-input submission can initialize the client's local
        # encryption state and be rejected. Retry only while the login page
        # explicitly remains present, never after navigation succeeds.
        for attempt in range(1, 4):
            time.sleep(3 if attempt == 1 else 1)
            if not fill_credentials_target(target, port, username, password):
                log("account login inputs disappeared before they could be filled")
                return 1
            time.sleep(1)
            value = evaluate_target(target, port, click_expression)
            if not value.get("ok"):
                log(f"credentials were filled but submit failed: {value.get('reason', 'unknown')}")
                return 1
            log(f"submitted the account login form (attempt {attempt})")
            for _ in range(10):
                time.sleep(1)
                result = evaluate_target(target, port, login_result_expression)
                if result.get("loggedIn"):
                    break
                if result.get("rejected") and result.get("stillLogin"):
                    break
            if result.get("loggedIn"):
                break
            if not result.get("stillLogin"):
                break
        else:
            log("account login was rejected after 3 attempts")
            return 1
    else:
        log("existing login session detected")

    if os.environ.get("CMCLOUD_AUTO_CONNECT", "1") != "1":
        return 0

    machine_name = os.environ.get("CMCLOUD_MACHINE_NAME", "").strip()
    connect_timeout = int(os.environ.get("CMCLOUD_CONNECT_TIMEOUT", "300"))
    connect_deadline = time.monotonic() + connect_timeout
    machine_name_json = json.dumps(machine_name, ensure_ascii=True)
    connect_expression = f"""
      (() => {{
        const requestedName = {machine_name_json};
        const visible = element => {{
          const style = getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
        }};
        const enterCommands = [...document.querySelectorAll('.enterImg.active')].filter(visible);
        const cards = [...document.querySelectorAll('.desktop-item .card-item')].filter(visible);
        let candidate = null;
        if (!requestedName && enterCommands.length >= 1) {{
          // The Electron list can keep a hidden clone while refreshing; the first
          // visible enter control is sufficient for the requested best-effort click.
          candidate = enterCommands[0];
        }} else if (requestedName) {{
          candidate = cards.find(card =>
            card.querySelector('.machine-name')?.textContent.trim() === requestedName
          );
        }} else if (cards.length === 1) {{
          candidate = cards[0];
        }} else {{
          candidate = document.querySelector('.desktop-item.active .card-item, .desktop-item .card-item.selected');
          if (candidate && !visible(candidate)) candidate = null;
        }}

        if (!candidate) {{
          const connectLabels = new Set(['连接', '立即连接', '进入云电脑', '进入桌面']);
          const commands = [...document.querySelectorAll('button, [role=button]')]
            .filter(element => visible(element) && !element.disabled)
            .filter(element => connectLabels.has(element.textContent.trim()));
          if (commands.length === 1) candidate = commands[0];
        }}

        if (!candidate) return {{ok: false, cardCount: cards.length, url: location.href}};
        candidate.click();
        return {{ok: true, url: location.href}};
      }})()
    """

    while time.monotonic() < connect_deadline:
        try:
            for candidate in list_targets(port):
                if candidate.get("type") != "page" or not candidate.get("webSocketDebuggerUrl"):
                    continue
                result = evaluate_target(candidate, port, connect_expression)
                if result.get("ok"):
                    suffix = f" named {machine_name!r}" if machine_name else ""
                    log(f"clicked the cloud computer connection{suffix}")
                    return 0
        except (OSError, ValueError, websocket.WebSocketException):
            pass
        time.sleep(2)

    log(f"no unambiguous cloud computer connection appeared within {connect_timeout}s")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
