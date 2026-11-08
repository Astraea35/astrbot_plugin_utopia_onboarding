from __future__ import annotations

import re

# These are conversational cues, never facts about another player's device.
HELPER_ADVICE = re.compile(
    r"^(?:你|您)(?:上次|之前|自己|的).{0,16}密码|"
    r"^(?:你|您).{0,12}(?:退出|重新登录|再输入|输入.{0,8}试|试一下|试试|空格)|"
    r"^(?:退出去?|重启|重新登录|换个地址|换条线路).{0,18}(?:再|试|输入)|"
    r"^(?:是不是|有没有一种可能).{0,12}(?:空格|密码|服务器地址)"
)
RESUME_HELP = re.compile(
    r"(?:继续|重新|再)(?:帮我|帮忙|协助|排查)|(?:现在|回来|回来了).{0,5}继续|"
    r"(?:我又|我想继续).{0,8}(?:进服|玩这个服|玩服务器)"
)
VAGUE_IMAGE_QUESTION = re.compile(
    r"^(?:这|这个|这步|它|那|那个).{0,5}(?:怎么|咋|如何|要|需要|啥|什么)|"
    r"^(?:怎么|咋|如何).{0,5}(?:弄|农|整|办|处理)[?？。!！]*$"
)
ADDRESS_QUESTION = re.compile(
    r"(?:地址|线路).{0,5}(?:多少|哪|几|换|[?？])|"
    r"^[一二三四五六123456](?:是|的)?(?:多少|哪个|在哪|呢)[?？。]*$|"
    r"^我只有[一二三四五六123456][。！!]*$"
)


def update_facts(previous: dict, messages: list[str]) -> dict:
    """Remember only device and progress explicitly stated by this player.

    Args:
        previous: Facts retained from this player's last answered request.
        messages: Chronological messages belonging to this player only.

    Returns:
        A bounded factual summary without credentials or other users' details.
    """
    facts = {"device": previous.get("device", ""), "stage": previous.get("stage", "")}
    tried = list(previous.get("tried", []))[-4:]
    for text in messages:
        if re.search(r"电脑|windows|\bpc\b|pcl", text, re.I) and not re.search(
            r"不是电脑|非电脑|不用电脑", text
        ):
            facts["device"] = "电脑"
        elif re.search(r"安卓|手机|fcl", text, re.I) and not re.search(
            r"不是手机|非安卓", text
        ):
            facts["device"] = "安卓手机" if "苹果" not in text else "苹果设备"
        if re.search(r"注册表|实体.*无法识别|unknown to this client|registry.?sync", text, re.I):
            facts["stage"] = "connection"
        elif re.search(r"官网|网站|网页", text):
            facts["stage"] = "website"
        elif re.search(r"数据|存档|领地|新号", text):
            facts["stage"] = "account_data"
        elif re.search(r"验证码|绑定|未绑定", text):
            facts["stage"] = "binding"
        elif re.search(r"密码|注册|登录|登陆|/login", text, re.I):
            facts["stage"] = "login"
        elif re.search(r"地址|线路", text) or ADDRESS_QUESTION.search(text):
            facts["stage"] = "address"
        elif re.search(r"解压|crc|压缩包|损坏", text, re.I):
            if facts["stage"] != "connection":
                facts["stage"] = "extract"
        elif re.search(
            r"下载|整合包|群文件|模组怎么装|本服的包|包从哪|包在哪|包咋|这个包|mod",
            text,
            re.I,
        ):
            if facts["stage"] != "connection":
                facts["stage"] = "download"
        elif re.search(r"启动|闪退|黑屏|加载", text):
            facts["stage"] = "launch"
        elif re.search(r"进不去|进不来|连不上|连接|卡吗|卡不卡|玩不了", text):
            # An unspecific complaint does not undo an already known failing step.
            facts["stage"] = facts["stage"] or "connection"
        if re.search(r"试过|都试|还是|不行|失败|错误|报错|不对|损坏", text):
            if text and text not in tried:
                tried.append(text[:120])
    facts["tried"] = tried[-4:]
    return facts


def stage_fallback(facts: dict, text: str) -> str:
    """Ask a useful, stage-specific question when all model attempts fail.

    Args:
        facts: Explicit same-player device and progress facts.
        text: Latest text, used only to identify a CRC error.

    Returns:
        A conservative next step without inventing server operations or addresses.
    """
    stage = facts.get("stage")
    device = facts.get("device")
    link = " 官网教程：https://mhwtb.shop/guide-start.html"
    if stage == "website":
        return (
            "官网页面暂时打不开的话，请把浏览器显示的错误文字发来。已在群里的玩家也可查看群文件和群公告里的下载信息。"
            + link
        )
    if stage == "address":
        return "请核对官网公布的服务器地址；群里提到的临时线路以管理组公告为准，我暂时无法核实额外地址。官网线路：https://mhwtb.shop/index.html#connect"
    if stage == "extract" and device == "电脑":
        if re.search(r"crc|损坏|校验", text, re.I):
            return (
                "先保留完整的 CRC／校验错误文字，核对下载是否完整，再尝试重新下载；不要继续使用报错的压缩包。"
                + link
            )
        return (
            "你已说明是电脑，当前卡在解压。请发出解压工具显示的完整错误文字，不用重做后面的进服步骤。"
            + link
        )
    if stage in {"download", "extract", "launch"}:
        if not device:
            return (
                "你用的是电脑还是安卓手机？请同时发出当前的完整错误文字，我按对应设备继续排查。"
                + link
            )
        return (
            f"按你已说明的{device}继续排查：请发出当前失败步骤和完整错误文字。暂时不要重复后面的注册或绑定操作。"
            + link
        )
    if stage == "login":
        return (
            "当前先排查登录，不要反复重新注册。请发出登录提示的错误文字；密码只在游戏里输入，不要发到群里。"
            + link
        )
    if stage == "binding":
        return (
            "请发出绑定失败时的提示文字；绑定只能使用你自己游戏界面当前显示的验证码，密码不要发到群里。"
            + link
        )
    return (
        "请发出当前卡住界面的完整错误文字；如果已经提供设备和步骤，我会沿着当前问题继续排查。"
        + link
    )
