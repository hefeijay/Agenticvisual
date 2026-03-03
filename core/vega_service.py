"""
Vega渲染服务
渲染Vega-Lite规范为图像
注意：需要Node.js环境和vega-cli
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, Any
import tempfile
import base64
import copy

from config.settings import Settings
from core.utils import app_logger, encode_image_to_base64

# 尝试导入 altair 作为替代渲染方案
try:
    import altair as alt
    import vl_convert as vlc
    ALTAIR_AVAILABLE = True
except ImportError:
    ALTAIR_AVAILABLE = False


class VegaService:
    """Vega rendering service"""
    
    def __init__(self):
        self.default_width = Settings.VEGA_DEFAULT_WIDTH
        self.default_height = Settings.VEGA_DEFAULT_HEIGHT
        self.require_cli = Settings.VEGA_REQUIRE_CLI
        self._check_rendering_capabilities()
        app_logger.info("Vega Service initialized")
    
    def _check_rendering_capabilities(self):
        """check the available rendering方案"""
        self.vega_cli_available = False
        self.vega_full_cli_available = False  # vg2png for full Vega specs
        self.altair_available = ALTAIR_AVAILABLE
        
        # check if vl2png (Vega-Lite) is available
        try:
            result = subprocess.run(
                ['vl2png', '--version'],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                self.vega_cli_available = True
                version = result.stdout.decode('utf-8').strip()
                app_logger.info(f"✅ vl2png (Vega-Lite) available: {version}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # check if vg2png (full Vega) is available
        try:
            result = subprocess.run(
                ['vg2png', '--version'],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                self.vega_full_cli_available = True
                version = result.stdout.decode('utf-8').strip()
                app_logger.info(f"✅ vg2png (full Vega) available: {version}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # if it is required to use CLI but CLI is not available
        if self.require_cli and not self.vega_cli_available:
            error_msg = (
                "\n" + "="*70 + "\n"
                " ERROR: VEGA_REQUIRE_CLI is set but vega-cli is not available!\n"
                "="*70 + "\n"
                "\n"
                "vega-cli is required but not found in your system.\n"
                "Please install Node.js and vega-cli to continue.\n"
                "\n"
                "Quick Installation Guide:\n"
                "\n"
                "macOS:\n"
                "  brew install node\n"
                "  npm install -g vega vega-lite vega-cli canvas\n"
                "\n"
                "Ubuntu/Debian:\n"
                "  curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -\n"
                "  sudo apt-get install -y nodejs\n"
                "  sudo apt-get install -y build-essential libcairo2-dev libpango1.0-dev libjpeg-dev libgif-dev librsvg2-dev\n"
                "  sudo npm install -g vega vega-lite vega-cli canvas\n"
                "\n"
                "Windows:\n"
                "  1. Download Node.js from https://nodejs.org/\n"
                "  2. Install Node.js\n"
                "  3. Open Command Prompt as Administrator\n"
                "  4. Run: npm install -g vega vega-lite vega-cli canvas\n"
                "\n"
                "After installation, verify with: vl2png --version\n"
                "\n"
                "For detailed instructions, see: NODEJS_VEGA_INSTALLATION.md\n"
                "="*70 + "\n"
            )
            app_logger.error(error_msg)
            raise RuntimeError(
                "vega-cli is required (VEGA_REQUIRE_CLI=True) but not found. "
                "Please install Node.js and vega-cli. See NODEJS_VEGA_INSTALLATION.md"
            )
        
        # 正常情况下的日志输出
        if not self.vega_cli_available:
            app_logger.warning("  vega-cli not found")
        
        # 报告可用的渲染方案
        if self.altair_available:
            app_logger.info(" altair/vl-convert available (Pure Python renderer)")
        
        if not self.vega_cli_available and not self.altair_available and not self.require_cli:
            app_logger.warning(
                "  WARNING: No chart renderer available!\n"
                "   System will use mock rendering (placeholder images).\n"
                "\n"
                "   To enable real chart rendering, choose one:\n"
                "\n"
                "   Option 1 - Pure Python (Recommended, No Node.js needed):\n"
                "   pip install altair vl-convert-python --break-system-packages\n"
                "\n"
                "   Option 2 - Node.js based (Higher quality):\n"
                "   1. Install Node.js from https://nodejs.org/\n"
                "   2. Run: npm install -g vega vega-lite vega-cli canvas\n"
                "\n"
                "   See documentation: NODEJS_VEGA_INSTALLATION.md\n"
            )
        elif not self.vega_cli_available and not self.require_cli:
            app_logger.info(
                "  Using altair for rendering (Pure Python).\n"
                "   For better quality, consider installing vega-cli:\n"
                "   1. Install Node.js: https://nodejs.org/\n"
                "   2. Run: npm install -g vega vega-lite vega-cli canvas\n"
            )
    
    def render(self, vega_spec: Dict, output_format: str = "png") -> Dict[str, Any]:
        """
        Render Vega-Lite or Vega specification to image.

        Priority:
          1. vega-cli (vl2png / vg2png) — highest quality
          2. vl-convert-python (vlc)    — pure Python, no Node.js required
          3. mock render (1×1 pixel)    — last resort, VLM will see a blank image
        """
        try:
            if self.require_cli:
                if not self.vega_cli_available and not self.vega_full_cli_available:
                    return {
                        "success": False,
                        "error": "vega-cli is required but not available. Please install Node.js and vega-cli.",
                    }
                return self._render_with_cli(vega_spec, output_format)

            is_full_vega = self._is_full_vega_spec(vega_spec)

            # 1. Try CLI
            if is_full_vega and self.vega_full_cli_available:
                return self._render_with_cli(vega_spec, output_format)
            if not is_full_vega and self.vega_cli_available:
                return self._render_with_cli(vega_spec, output_format)

            # 2. Try vl-convert (pure Python)
            if self.altair_available and not is_full_vega:
                result = self._render_with_vlconvert(vega_spec)
                if result.get("success"):
                    return result

            # 3. Fallback mock
            app_logger.warning("No real renderer available, using mock (blank) rendering")
            return self._mock_render(vega_spec)

        except Exception as e:
            app_logger.error(f"Render error: {e}")
            return {"success": False, "error": str(e)}
    
    def _is_full_vega_spec(self, vega_spec: Dict) -> bool:
        """check if it is a full Vega specification (rather than Vega-Lite)"""
        schema = vega_spec.get("$schema", "")
        # Vega schema contains /vega/ but not /vega-lite/
        if "vega-lite" in schema.lower():
            return False
        if "/vega/" in schema.lower() or "vega/v" in schema.lower():
            return True
        # if there are signals or scales top-level fields, it is usually Vega
        if "signals" in vega_spec or ("scales" in vega_spec and "encoding" not in vega_spec):
            return True
        return False
    
    def _render_with_cli(self, vega_spec: Dict, output_format: str = "png") -> Dict[str, Any]:
        """render with vega-cli (automatically select vl2png or vg2png)"""
        try:
            # 检测规范类型
            is_full_vega = self._is_full_vega_spec(vega_spec)
            
            if is_full_vega:
                if not self.vega_full_cli_available:
                    return {
                        "success": False,
                        "error": "Full Vega spec detected but vg2png is not available. Please install: npm install -g vega vega-cli"
                    }
                cli_cmd = 'vg2png'
                renderer_name = "vega-cli (vg2png)"
            else:
                if not self.vega_cli_available:
                    return {
                        "success": False,
                        "error": "Vega-Lite spec but vl2png is not available. Please install: npm install -g vega-lite vega-cli"
                    }
                cli_cmd = 'vl2png'
                renderer_name = "vega-cli (vl2png)"
            
            # create a temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as spec_file:
                json.dump(vega_spec, spec_file)
                spec_path = spec_file.name
            
            output_path = spec_path.replace('.json', f'.{output_format}')
            
            subprocess.run([
                cli_cmd,
                spec_path,
                output_path
            ], check=True, capture_output=True, timeout=30)  # increase the timeout time
            
            # read the generated image
            image_base64 = encode_image_to_base64(output_path)
            
            app_logger.info(f" Rendered using {renderer_name}")
            return {
                "success": True,
                "image_base64": image_base64,
                "image_path": output_path,
                "renderer": renderer_name
            }
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            error_msg = f"vega-cli execution failed: {e}"
            app_logger.error(error_msg)
            
            if self.require_cli:
                # if it is required to use CLI only, return an error
                return {
                    "success": False,
                    "error": error_msg,
                    "help": "Please check vega-cli installation. Run: vl2png --version or vg2png --version"
                }
            else:
                # otherwise use mock rendering
                app_logger.warning(
                    "Something wrong. The real data is not rendered.\n" 
                )
                return self._mock_render(vega_spec)
    
    def _render_with_vlconvert(self, vega_spec: Dict) -> Dict[str, Any]:
        """Pure-Python rendering via vl-convert-python (no Node.js needed)."""
        try:
            import vl_convert as vlc  # noqa: PLC0415
            spec_str = json.dumps(vega_spec, ensure_ascii=False)
            png_bytes = vlc.vegalite_to_png(vl_spec=spec_str, scale=2)
            image_base64 = base64.b64encode(png_bytes).decode("utf-8")
            app_logger.info("Rendered using vl-convert (pure Python)")
            return {
                "success": True,
                "image_base64": image_base64,
                "image_path": None,
                "renderer": "vl-convert",
            }
        except Exception as e:
            app_logger.warning(f"vl-convert rendering failed: {e}")
            return {"success": False, "error": str(e)}

    def _mock_render(self, vega_spec: Dict) -> Dict:
        """
        mock rendering (return a placeholder image)
        
        when vega-cli and altair are both unavailable
        """
        app_logger.info(
            "  Using mock rendering (placeholder image).\n"
            "   For real charts, see VEGA_CLI_INSTALLATION.md"
        )
        
        # return a simple 1x1 pixel placeholder (white)
        mock_image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        return {
            "success": True,
            "image_base64": mock_image,
            "image_path": None,
            "renderer": "mock",
            "warning": "Using mock rendering. Install vega-cli or altair for real charts."
        }
    
    def validate_spec(self, vega_spec: Dict) -> Dict[str, Any]:
        """validate the Vega-Lite specification"""
        required_fields = ["mark", "encoding"]
        missing = [f for f in required_fields if f not in vega_spec]
        
        if missing:
            return {
                "valid": False,
                "error": f"Missing required fields: {missing}"
            }
        return {"valid": True}
    
    def update_spec(self, vega_spec: Dict, updates: Dict) -> Dict:
        """update the Vega-Lite specification"""
        new_spec = copy.deepcopy(vega_spec)  # 使用copy.deepcopy代替JSON序列化
        new_spec.update(updates)
        return new_spec


_vega_service = None

def get_vega_service() -> VegaService:
    """get the Vega service singleton"""
    global _vega_service
    if _vega_service is None:
        _vega_service = VegaService()
    return _vega_service
