import aiohttp
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig

@register("atmosphere", "RC-CHN", "监控并转发到Webhook", "1.1.0")
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.config.save_config()

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        logger.info(f"加载 atmosphere 插件，配置: {self.config}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent, *args, **kwargs):
        """监听所有消息，如果发送者或群组在目标列表中，则打印消息详情并推送到webhook。"""
        target_umos = self.config.get("target_umo", [])
        target_group_ids = self.config.get("target_group_id", [])
        
        sender_id = event.get_sender_id()
        message_obj = event.message_obj
        group_id = message_obj.group_id
        
        logger.debug(f"收到消息，消息类型: {message_obj.type}, 发送者: {sender_id}, 群组ID: {group_id or '无'}")

        trigger_reason = None
        if sender_id in target_umos:
            trigger_reason = f"目标用户 {sender_id}"
        elif group_id and group_id in target_group_ids:
            trigger_reason = f"目标群组 {group_id}"

        if trigger_reason:
            # 记录详细日志
            self.log_message_details(message_obj, trigger_reason)
            
            # 推送到 Webhook
            webhook_url = self.config.get("webhook_url")
            if webhook_url:
                await self.send_to_webhook(message_obj, trigger_reason, webhook_url)

    def log_message_details(self, message_obj, trigger_reason):
        """格式化并记录消息的详细信息。"""
        sender_details = f"ID: {message_obj.sender.user_id}, 昵称: {message_obj.sender.nickname}"
        if hasattr(message_obj.sender, "card") and message_obj.sender.card:
            sender_details += f", 群名片: {message_obj.sender.card}"

        message_chain_details = []
        for comp in message_obj.message:
            comp_name = type(comp).__name__
            if comp_name == "Plain":
                message_chain_details.append(f"    - 文本(Plain): '{comp.text}'")
            elif comp_name == "At":
                message_chain_details.append(f"    - @(At): qq={comp.qq}")
            elif comp_name == "Image":
                img_summary = [f"{k}={v}" for k, v in comp.__dict__.items() if v]
                message_chain_details.append(f"    - 图片(Image): {', '.join(img_summary)}")
            else:
                message_chain_details.append(f"    - {comp_name}: {str(comp)}")
        
        message_chain_str = "\n".join(message_chain_details)

        log_message = (
            f"捕获到来自 {trigger_reason} 的消息:\n"
            f"  - 消息ID: {message_obj.message_id}\n"
            f"  - 发送者: {sender_details}\n"
            f"  - 消息链 (解析后):\n{message_chain_str}"
        )
        logger.debug(log_message)

    async def send_to_webhook(self, message_obj, trigger_reason, url):
        """将消息对象序列化并发送到指定的Webhook URL。"""
        payload = {
            "trigger_reason": trigger_reason,
            "type": message_obj.type.name,
            "self_id": message_obj.self_id,
            "session_id": message_obj.session_id,
            "message_id": message_obj.message_id,
            "group_id": message_obj.group_id,
            "sender": message_obj.sender.__dict__,
            "message": [comp.__dict__ for comp in message_obj.message],
            "message_str": message_obj.message_str,
            "timestamp": message_obj.timestamp
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as response:
                    if 200 <= response.status < 300:
                        logger.info(f"成功将消息推送到 webhook，状态码: {response.status}")
                    else:
                        logger.error(f"推送到 webhook 失败，状态码: {response.status}, 响应: {await response.text()}")
        except Exception as e:
            logger.error(f"推送 webhook 时发生异常: {e}")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
