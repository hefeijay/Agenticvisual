"""
VLM调用服务（OpenRouter API）
使用 OpenAI 兼容接口，支持多模态视觉模型
"""

from typing import Dict, List, Any, Optional

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("Warning: openai package not installed. Using mock VLM service.")

from config.settings import Settings
from core.utils import app_logger, extract_json_from_text


def _convert_to_openai_content(content: List) -> List:
    """将内部消息格式转换为 OpenAI/OpenRouter 多模态格式"""
    openai_content = []
    for item in content:
        if isinstance(item, str):
            openai_content.append({"type": "text", "text": item})
        elif isinstance(item, dict):
            if "text" in item:
                openai_content.append({"type": "text", "text": item["text"]})
            elif "image" in item:
                img_url = item["image"]
                if not img_url.startswith("data:"):
                    img_url = f"data:image/png;base64,{img_url}"
                openai_content.append({
                    "type": "image_url",
                    "image_url": {"url": img_url, "detail": "high"}
                })
            else:
                openai_content.append({"type": "text", "text": str(item)})
        else:
            openai_content.append({"type": "text", "text": str(item)})
    return openai_content


class VLMService:
    """VLM调用服务（OpenRouter）"""
    
    def __init__(self):
        self.client = None
        if OPENAI_AVAILABLE and Settings.OPENROUTER_API_KEY:
            self.client = OpenAI(
                api_key=Settings.OPENROUTER_API_KEY,
                base_url=Settings.OPENROUTER_BASE_URL,
                timeout=Settings.VLM_TIMEOUT,
            )
        self.model = Settings.VLM_MODEL
        self.max_tokens = Settings.VLM_MAX_TOKENS
        self.temperature = Settings.VLM_TEMPERATURE
        app_logger.info(f"VLM Service initialized (OpenRouter): {self.model}")
    
    def call(self, messages: List[Dict], system_prompt: str = None, 
             expect_json: bool = False) -> Dict:
        """调用VLM"""
        if not OPENAI_AVAILABLE or not self.client:
            return self._mock_call(messages, system_prompt, expect_json)
        
        try:
            api_messages = self._prepare_messages(messages, system_prompt)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            
            if not response or not response.choices:
                err_msg = "API returned no choices (可能原因: 模型不支持视觉输入/配额不足/内容过滤)"
                try:
                    raw = str(response) if response else "response is None"
                    app_logger.error(f"❌ {err_msg}. raw: {raw}")
                except Exception:
                    pass
                return {"success": False, "error": err_msg}
            
            choice = response.choices[0]
            msg = choice.message
            
            # 处理 finish_reason 为 content_filter 等情况
            if choice.finish_reason and choice.finish_reason not in ("stop", "end_turn"):
                app_logger.warning(f"VLM finish_reason: {choice.finish_reason}")
            
            content = msg.content if msg else None
            
            if content:
                app_logger.info(f"🤖 VLM原始输出前500字符: {content[:500]}")
                result = {"success": True, "content": content}
                if expect_json:
                    result["parsed_json"] = extract_json_from_text(content)
                return result
            else:
                app_logger.error("❌ VLM 返回空内容")
                return {"success": False, "error": "Empty response"}
                
        except Exception as e:
            app_logger.error(f"❌ VLM调用异常: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _prepare_messages(self, messages: List, system_prompt: str = None) -> List:
        """准备 OpenRouter/OpenAI API 消息格式"""
        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", [])
            if isinstance(content, str):
                content = [{"text": content}]
            openai_content = _convert_to_openai_content(content)
            api_messages.append({"role": role, "content": openai_content})
        return api_messages
    
    def _mock_call(self, messages, system_prompt, expect_json):
        """Mock调用（用于测试）"""
        mock_response = {
            "success": True,
            "content": "这是一个模拟响应。请安装 openai 包并设置 OPENROUTER_API_KEY 以使用真实的 VLM 服务。"
        }
        if expect_json:
            mock_response["parsed_json"] = {"mock": True}
        return mock_response
    
    def call_with_image(self, text: str, image_base64: str, 
                       system_prompt: str = None, expect_json: bool = False):
        """便捷方法：文本+图像"""
        messages = [{
            "role": "user",
            "content": [
                {"text": text},
                {"image": f"data:image/png;base64,{image_base64}"}
            ]
        }]
        return self.call(messages, system_prompt, expect_json)
    
    def call_text_only(self, text: str, system_prompt: str = None, 
                       expect_json: bool = False):
        """便捷方法：仅文本"""
        messages = [{"role": "user", "content": [{"text": text}]}]
        return self.call(messages, system_prompt, expect_json)


_vlm_service = None

def get_vlm_service() -> VLMService:
    """获取VLM服务单例"""
    global _vlm_service
    if _vlm_service is None:
        _vlm_service = VLMService()
    return _vlm_service
