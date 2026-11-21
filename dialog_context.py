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
OUTSIDE_ONBOARDING = re.compile(
    r"(?:文件|模组|mod|插件|数据包).{0,24}(?:转换|转成|移植|适配|定制|开发)|"
    r"(?:转换|转成|移植|适配|定制|开发).{0,24}(?:服务器版本|服务端|模组|mod|插件)|"
    r"(?:光影|材质|资源包).{0,24}(?:月亮|太阳|天空|颜色|画面|好看|效果|显示|问题)|"
    r"(?:月亮|太阳|天空).{0,16}(?:光影|材质)|"
    r"地址卡|(?:画|制作|生成|设计).{0,12}(?:地址图|宣传图|海报)",
    re.I,
)
ENTRY_FAILURE = re.compile(
    r"进不去|进不来|连不上|无法连接|连接失败|未绑定|验证码.{0,8}过期|"
    r"(?:游戏|客户端|启动器).{0,8}(?:闪退|崩溃|黑屏|启动不了|打不开)|"
    r"(?:安装|下载|解压).{0,8}(?:失败|报错|错误|不了|损坏)|"
    r"注册表.{0,12}(?:失败|不匹配)|(?:实体|注册项|条目).{0,12}(?:无法识别|缺失)",
    re.I,
)

MAID_MOD = r"(?:车[万萬]女仆|touhou_little_maid|touhou little maid(?:: orihime)?)"
MAID_MISSING = re.compile(
    rf"(?:(?:(?P<self>我(?:这边|的客户端)?(?:确实|才发现)?)[，, ]*"
    rf"|(?P<error>(?:游戏|客户端|报错)?提示)[：: ]*)?"
    rf"(?:没(?:有)?装|缺(?:少|失)?|找不到)[：: ]*(?:模组[：: ]*)?{MAID_MOD}"
    rf"|(?P<english>missing(?: required)? mod[：: ]+{MAID_MOD}|mod[：: ]+{MAID_MOD} is missing))"
    r"(?:[ ]*(?:模组|mod))?(?:了|啊|呀)?[。！! ]*",
    re.I,
)
MAID_MOD_GUIDE = (
    "如果你已经装好了本服整合包，只缺车万女仆，先退出游戏，从群文件取本服提供的 Fabric 版车万女仆"
    "（touhou_little_maid），把 .jar 放进启动器当前选中的乌托邦实例的 mods 文件夹，然后重新启动游戏。"
    "找不到对应文件或还缺其他模组时，从群文件的「安装」文件夹下载当前完整整合包。"
    "如果已按这两种方式之一更新，仍提示缺失或不匹配，请把完整报错截图交给管理组核对版本。"
    "教程：https://mhwtb.shop/guide-start.html#download-qq"
)


def reports_missing_maid(text: str, active: bool) -> bool:
    """Allow a terse missing-mod update in the same player's help conversation."""
    match = MAID_MISSING.fullmatch(text.strip())
    return bool(match and (active or match["self"] or match["error"] or match["english"]))


def is_outside_onboarding(text: str) -> bool:
    """Exclude development and cosmetic chat while retaining explicit entry failures."""
    return bool(OUTSIDE_ONBOARDING.search(text) and not ENTRY_FAILURE.search(text))


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
        if re.search(
            r"注册表|实体.*无法识别|unknown to this client|registry.?sync", text, re.I
        ):
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
