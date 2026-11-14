from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Plain

PRESENCE = re.compile(
    r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+) \+08:00 \[INF\] "
    r"\[(加入|退出)\]\[乌托邦探险之旅\] ([A-Za-z0-9_]{1,16})\s*$"
)
PACK_REMINDER = (
    "检测到你绑定后刚进服就断开了，可能是没有使用服务器完整整合包，或模组／配置缺失、版本不一致。"
    "请从群文件或官网获取当前服务器完整安装包，按对应设备的教程安装并启动包内版本，"
    "不要只复制 mods；若已使用群里的包仍报错，也可能是压缩包本身有问题，请保留完整断开提示截图交管理组核查。"
    "教程：https://mhwtb.shop/guide-start.html"
)


class EasyBotMonitor:
    def __init__(self, plugin):
        self.plugin = plugin
        directory = plugin.config.get("easybot_dir", "").strip()
        self.root = Path(directory) if directory else None
        self.joins = {}
        self.state_path = plugin.data_dir / "quick_exit_reminders.json"
        try:
            self.sent = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(self.sent, dict):
                self.sent = {}
        except (OSError, ValueError):
            self.sent = {}

    def binding(self, *, player=None, qq=None, at=None):
        if self.root is None:
            return None
        at = time.time() if at is None else at
        clause, value = (
            ("p.Name = ? COLLATE NOCASE", player) if player else ("s.Uuid = ?", qq)
        )
        with sqlite3.connect(
            (self.root / "EasyBot.db").as_uri() + "?mode=ro", uri=True, timeout=1
        ) as db:
            rows = db.execute(
                "SELECT p.Name, s.Uuid, p.CreatedTime FROM Player p "
                "JOIN PlayerSocialAccount ps ON ps.UsersId=p.Id "
                "JOIN SocialAccount s ON s.Id=ps.SocialAccountsId "
                "WHERE lower(s.Platform)='qq' AND " + clause,
                (value,),
            ).fetchall()
        candidates = []
        for name, user, created in rows:
            if (
                re.fullmatch(r"[1-9]\d{4,11}", str(user))
                and 0 <= at - datetime.fromisoformat(created).timestamp() <= 86400
            ):
                candidates.append((str(name), str(user)))
        return candidates[0] if len({user for _, user in candidates}) == 1 else None

    async def consume(self, line):
        match = PRESENCE.fullmatch(line.strip())
        if not match:
            return
        when, action, name = match.groups()
        at = datetime.fromisoformat(when).timestamp()
        if not 0 <= time.time() - at <= 60:
            return
        self.joins = {
            key: value for key, value in self.joins.items() if at - value <= 30
        }
        key = name.casefold()
        if action == "加入":
            self.joins.setdefault(key, at)
            return
        joined = self.joins.pop(key, None)
        if joined is None or not 0 <= at - joined <= 30:
            return
        binding = await asyncio.to_thread(self.binding, player=name, at=at)
        if binding is None or self.plugin.stopping:
            return
        _, qq = binding
        platform = self.plugin.context.get_platform("aiocqhttp")
        if platform is None:
            return
        for group in self.plugin.config.get("group_ids", []):
            group = str(group)
            marker = group + ":" + qq
            if at - self.sent.get(marker, 0) < 86400:
                continue
            delivered = await self.plugin.context.send_message(
                platform.meta().id + ":GroupMessage:" + group,
                MessageChain(chain=[At(qq=qq), Plain(text=" " + PACK_REMINDER)]),
            )
            if delivered is False:
                logger.warning("Utopia quick-exit reminder delivery unconfirmed")
                continue
            self.sent[marker] = at
            self.sent = {k: v for k, v in self.sent.items() if at - v < 86400}
            temporary = self.state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.sent), encoding="utf-8")
            temporary.replace(self.state_path)
            now = time.monotonic()
            self.plugin.sessions[(group, qq)] = {
                "at": now,
                "last_help_at": now,
                "image_followup_open": True,
                "facts": {"stage": "connection", "device": "", "tried": []},
                "history": [{"role": "assistant", "content": PACK_REMINDER}],
            }
            logger.info(
                "Utopia quick-exit reminder delivered: group=%s duration=%.3fs",
                group,
                at - joined,
            )

    async def run(self):
        if self.root is None:
            logger.info(
                "Utopia EasyBot monitor disabled: no installation directory configured"
            )
            return
        path = self.root / "logs/latest.log"
        opener = None
        if os.name == "nt":
            import ctypes
            import msvcrt
            from ctypes import wintypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            create_file = kernel.CreateFileW
            create_file.argtypes = [
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.LPVOID,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.HANDLE,
            ]
            create_file.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]

            def opener(filename, flags):
                # Allow EasyBot to delete or rename its log during startup.
                handle = create_file(filename, 0x80000000, 0x7, None, 3, 0x80, None)
                if handle == wintypes.HANDLE(-1).value:
                    raise ctypes.WinError(ctypes.get_last_error())
                try:
                    return msvcrt.open_osfhandle(handle, flags)
                except BaseException:
                    kernel.CloseHandle(handle)
                    raise

        stream = None
        try:
            while not self.plugin.stopping:
                try:
                    if stream is None:
                        stream = open(
                            path, encoding="utf-8", errors="replace", opener=opener
                        )
                        stream.seek(0, 2)
                        logger.info("Utopia EasyBot quick-exit monitor started")
                    stat = path.stat()
                    if (
                        stat.st_size < stream.tell()
                        or stat.st_ino != os.fstat(stream.fileno()).st_ino
                    ):
                        stream.close()
                        stream = open(
                            path, encoding="utf-8", errors="replace", opener=opener
                        )
                    while True:
                        position = stream.tell()
                        line = stream.readline()
                        if not line.endswith("\n"):
                            stream.seek(position)
                            break
                        try:
                            await self.consume(line)
                        except Exception as error:
                            logger.warning(
                                "Utopia quick-exit processing failed: error=%s",
                                type(error).__name__,
                            )
                except OSError:
                    if stream:
                        stream.close()
                        stream = None
                await asyncio.sleep(0.5)
        finally:
            if stream:
                stream.close()
