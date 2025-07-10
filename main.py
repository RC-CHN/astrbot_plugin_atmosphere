import asyncio
import aiohttp
import json
from multiprocessing import Process, Queue

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import astrbot.core.message.components as Comp
from astrbot.core.message.message_event_result import MessageChain

# Use a relative import for the local api module
from .api import run_server

@register("atmosphere", "RC-CHN", "双向 Webhook 消息收发插件", "2.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.config.save_config()

        # For inbound messages from API
        self.in_queue: Queue | None = None
        self.process: Process | None = None
        self._running = False

    async def initialize(self):
        """初始化插件，根据配置启动 API 服务。"""
        logger.info("初始化 Atmosphere 插件...")
        
        if self.config.get("api_enabled"):
            self.start_api_server()
        else:
            logger.info("API 服务未启用，跳过启动。")

    def start_api_server(self):
        """启动 FastAPI 服务子进程。"""
        host = self.config.get("api_host", "0.0.0.0")
        port = self.config.get("api_port", 9968)
        webhook_path = self.config.get("api_webhook_path", "/forward")
        token = self.config.get("api_preshared_token", "")
        
        self.forward_target_umos = self.config.get("forward_target_umo", [])
        if not self.forward_target_umos:
            logger.warning("API 服务已启用，但未配置 'forward_target_umo'，收到的消息将不会被转发。")

        self.in_queue = Queue()
        self.process = Process(
            target=run_server,
            args=(host, port, webhook_path, token, self.in_queue),
            daemon=True,
        )
        self.process.start()
        self._running = True
        asyncio.create_task(self._process_inbound_messages())
        logger.info(f"API 服务已启动，监听 http://{host}:{port}/{webhook_path.strip('/')}")

    async def _process_inbound_messages(self):
        """处理来自 API 子进程队列的消息，并转发。"""
        if not self.in_queue:
            return

        while self._running:
            try:
                message_text = await asyncio.get_event_loop().run_in_executor(None, self.in_queue.get)
                if message_text is None:
                    break
                
                logger.info(f"从 API 收到消息: '{message_text}'")
                chain = MessageChain(chain=[Comp.Plain(text=message_text)])
                
                for umo in self.forward_target_umos:
                    try:
                        await self.context.send_message(umo, chain)
                        logger.info(f"成功将 API 消息转发至 UMO: {umo}")
                    except Exception as e:
                        logger.error(f"转发 API 消息至 UMO {umo} 失败: {e}")

            except (EOFError, BrokenPipeError):
                logger.info("API 消息队列已关闭。")
                self._running = False
                break
            except Exception as e:
                logger.error(f"处理 API 消息时发生未知错误: {e}", exc_info=True)
                await asyncio.sleep(1)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent, *args, **kwargs):
        """监听所有消息，如果满足条件，则推送到外部 Webhook。"""
        target_umos = self.config.get("monitor_target_umos", [])
        target_group_ids = self.config.get("monitor_target_group_ids", [])
        webhook_url = self.config.get("monitor_webhook_url")

        if not webhook_url:
            return

        sender_id = event.get_sender_id()
        message_obj = event.message_obj
        group_id = message_obj.group_id
        
        trigger_reason = None
        if sender_id in target_umos:
            trigger_reason = f"目标用户 {sender_id}"
        elif group_id and group_id in target_group_ids:
            trigger_reason = f"目标群组 {group_id}"

        if trigger_reason:
            logger.debug(f"捕获到来自 {trigger_reason} 的消息，准备推送到 Webhook。")
            await self.send_to_webhook(message_obj, trigger_reason, webhook_url)

    def _serialize_for_json(self, obj):
        """Safely serialize an object for JSON by converting non-serializable parts to strings."""
        if hasattr(obj, '__dict__'):
            serializable_dict = {}
            for key, value in obj.__dict__.items():
                if key.startswith('_'):
                    continue
                try:
                    json.dumps(value)
                    serializable_dict[key] = value
                except TypeError:
                    serializable_dict[key] = str(value)
            return serializable_dict
        return str(obj)

    async def send_to_webhook(self, message_obj, trigger_reason, url):
        """将消息对象序列化并发送到指定的Webhook URL。"""
        payload = {
            "trigger_reason": trigger_reason,
            "type": message_obj.type.name,
            "self_id": message_obj.self_id,
            "session_id": message_obj.session_id,
            "message_id": message_obj.message_id,
            "group_id": message_obj.group_id,
            "sender": self._serialize_for_json(message_obj.sender),
            "message": [self._serialize_for_json(comp) for comp in message_obj.message],
            "message_str": message_obj.message_str,
            "timestamp": message_obj.timestamp
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as response:
                    if 200 <= response.status < 300:
                        logger.info(f"成功将消息推送到 Webhook，状态码: {response.status}")
                    else:
                        logger.error(f"推送到 Webhook 失败，状态码: {response.status}, 响应: {await response.text()}")
        except Exception as e:
            logger.error(f"推送 Webhook 时发生异常: {e}")

    async def terminate(self):
        """停止插件和 API 服务子进程。"""
        logger.info("正在终止 Atmosphere 插件...")
        self._running = False
        
        if self.in_queue:
            try:
                self.in_queue.put_nowait(None)
            except Exception:
                pass

        if self.process and self.process.is_alive():
            logger.info("正在终止 API 服务进程...")
            self.process.terminate()
            try:
                await asyncio.get_event_loop().run_in_executor(None, self.process.join, 5)
                if self.process.is_alive():
                    logger.warning("API 进程在5秒后未能终止，将强制终止。")
                    self.process.kill()
            except Exception as e:
                logger.error(f"终止 API 进程时发生错误: {e}")
        
        if self.in_queue:
            self.in_queue.close()
            self.in_queue.join_thread()

        logger.info("Atmosphere 插件已成功终止。")
