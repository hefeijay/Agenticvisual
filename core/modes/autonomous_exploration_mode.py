"""自主探索模式（简化版 - 使用 vega_spec）"""
from typing import Dict, List
import time
import copy
from core.vlm_service import get_vlm_service
from core.vega_service import get_vega_service
from tools import get_tool_executor
from prompts import get_prompt_manager
from config.settings import Settings
from core.utils import app_logger, get_spec_data_count


class AutonomousExplorationMode:
    """自主探索模式"""
    
    def __init__(self):
        self.vlm = get_vlm_service()
        self.vega = get_vega_service()
        self.tool_executor = get_tool_executor()
        self.prompt_mgr = get_prompt_manager()
    
    def execute(self, user_query: str, vega_spec: Dict,
                image_base64: str, chart_type, context: Dict = None,
                event_callback=None) -> Dict:
        """执行自主探索分析（按DashScope标准多轮对话格式）"""
        system_prompt = self.prompt_mgr.assemble_system_prompt(
            chart_type=chart_type,
            mode="autonomous_exploration",
            include_tools=True
        )

        def _emit(event_type: str, data: dict):
            if event_callback:
                try:
                    event_callback(event_type, data)
                except Exception:
                    pass

        # 从context读取messages历史
        messages = context.get('autonomous_messages', []) if context else []
        explorations = context.get('autonomous_explorations', []) if context else []

        # 首次调用：初始化第一条user消息；续探：追加新方向
        if len(messages) == 0:
            messages.append({
                "role": "user",
                "content": [
                    {"text": f"Autonomously explore this view. Exploration direction: {user_query}"},
                    {"image": f"data:image/png;base64,{image_base64}"}
                ]
            })
        else:
            messages.append({
                "role": "user",
                "content": [
                    {"text": f"Continue exploring. New direction: {user_query}"},
                    {"image": f"data:image/png;base64,{image_base64}"}
                ]
            })
        
        # 保存原始 vega_spec，用于 reset_view 工具
        original_vega_spec = copy.deepcopy(vega_spec)
        
        current_spec = vega_spec
        current_image = image_base64
        
        for iteration in range(Settings.MAX_EXPLORATION_ITERATIONS):
            iteration_start = time.time()
            _emit("iteration.started", {"iteration": iteration + 1, "user_query": user_query})

            app_logger.info(f"探索第{iteration+1}轮 - messages数量: {len(messages)}")
            for idx, msg in enumerate(messages):
                role = msg['role']
                content_items = len(msg.get('content', []))
                has_image = any('image' in c for c in msg.get('content', []))
                app_logger.info(f"  消息{idx}: role={role}, items={content_items}, 含图片={has_image}")
            
            # 调用VLM（直接传messages）
            response = self.vlm.call(messages, system_prompt, expect_json=True)
            
            #如果调用失败，返回提示
            if not response.get("success"):
                app_logger.error(f" 探索第{iteration+1}轮VLM失败: {response.get('error')}")
                explorations.append({
                    "iteration": iteration + 1,
                    "success": False,
                    "error": response.get('error'),
                    "duration": time.time() - iteration_start
                })
                break
            
            # 直接追加VLM返回的assistant消息（按DashScope标准）
            analysis = response.get("parsed_json", {})
            assistant_message = {
                "role": "assistant",
                "content": [{"text": response.get("content", "")}]
            }
            messages.append(assistant_message)
            _emit("agent.message", {
                "iteration": iteration + 1,
                "text": response.get("content", ""),
                "key_insights": analysis.get("key_insights", []),
                "reasoning": analysis.get("reasoning", "")
            })

            #  添加调试日志：检查JSON提取结果
            app_logger.info(f" JSON提取结果:")
            app_logger.info(f"  - tool_call: {analysis.get('tool_call')}")
            app_logger.info(f"  - exploration_complete: {analysis.get('exploration_complete')}")
            app_logger.info(f"  - key_insights数量: {len(analysis.get('key_insights', []))}")
            
            app_logger.info(f" 探索第{iteration+1}轮完成")
            
            # 记录迭代
            iteration_record = {
                "iteration": iteration + 1,
                "success": True,
                "timestamp": time.time(),
                "vlm_raw_output": response.get("content", ""),  # 保存VLM原始输出
                "images": [current_image],
                "analysis_summary": {
                    "key_insights": analysis.get("key_insights", []),
                    "reasoning": analysis.get("reasoning", ""),
                }
            }
            
            # 执行工具
            if analysis.get("tool_call"):
                tool_name = analysis["tool_call"]["tool"]
                tool_params = analysis["tool_call"].get("params", {})
                tool_params['vega_spec'] = current_spec
                # 只有需要context的工具才传递
                if tool_name in ('reset_view', 'undo_view'):
                    tool_params['context'] = context

                _emit("tool.started", {
                    "iteration": iteration + 1,
                    "tool_name": tool_name,
                    "tool_input": {k: v for k, v in tool_params.items() if k not in ('vega_spec', 'context')}
                })
                app_logger.info(f"Executing tool: {tool_name}")
                tool_result = self.tool_executor.execute(tool_name, tool_params)
                
                tool_result_clean = {k: v for k, v in tool_result.items() if k != 'vega_spec'}
                _emit("tool.finished", {
                    "iteration": iteration + 1,
                    "tool_name": tool_name,
                    "tool_result": tool_result_clean,
                    "success": tool_result.get("success", False)
                })

                # 保存tool_result（排除vega_spec避免序列化问题和数据冗余）
                iteration_record["tool_execution"] = {
                    "tool_name": tool_name,
                    "tool_params": {k: v for k, v in tool_params.items() if k not in ('vega_spec', 'context')},
                    "tool_result": tool_result_clean
                }

                if tool_result.get("success"):
                    # 工具执行成功
                    if "vega_spec" in tool_result:
                        # 有新的vega_spec，更新并重新渲染
                        # 先将旧 spec 入栈（排除 reset/undo）
                        if tool_name not in ['reset_view', 'undo_view']:
                            if context is not None:
                                history = context.setdefault("spec_history", [])
                                history.append(copy.deepcopy(current_spec))

                        current_spec = tool_result["vega_spec"]

                        # 若会话存在大数据管理器，按区域补点
                        current_spec = self._apply_data_manager(current_spec, context)
                        render_result = self.vega.render(current_spec)

                        if render_result.get("success"):
                            current_image = render_result["image_base64"]
                            iteration_record["images"].append(current_image)
                            _emit("view.updated", {
                                "iteration": iteration + 1,
                                "spec": current_spec,
                                "tool_name": tool_name
                            })

                            success_msg = tool_result.get("message", "Operation completed")
                            messages.append({
                                "role": "user",
                                "content": [
                                    {"text": f"Tool {tool_name} succeeded.\n\nResult: {success_msg}\n\nHere is the updated view:"},
                                    {"image": f"data:image/png;base64,{current_image}"}
                                ]
                            })
                            app_logger.info(f"Re-rendered after {tool_name}: {success_msg}")
                        else:
                            render_error = render_result.get('error', 'Render failed')
                            app_logger.error(f"Render failed: {render_error}")
                            iteration_record["success"] = False
                            
                            messages.append({
                                "role": "user",
                                "content": [
                                    {"text": f"Tool {tool_name} render failed: {render_error}\n\nCurrent view (unchanged):"},
                                    {"image": f"data:image/png;base64,{current_image}"}
                                ]
                            })
                    else:
                        # 没有vega_spec（分析型工具）
                        success_msg = tool_result.get("message", str(tool_result))
                        messages.append({
                            "role": "user",
                            "content": [
                                {"text": f"Tool {tool_name} succeeded.\n\nAnalysis result: {success_msg}\n\nView unchanged, current view:"},
                                {"image": f"data:image/png;base64,{current_image}"}
                            ]
                        })
                        app_logger.info(f"Tool {tool_name} completed (analysis): {success_msg}")
                else:
                    # 工具执行失败
                    error_msg = tool_result.get("error", "Unknown error")
                    messages.append({
                        "role": "user",
                        "content": [
                            {"text": f"Tool {tool_name} failed.\n\nError: {error_msg}\n\nPlease try a different exploration direction.\n\nCurrent view (unchanged):"},
                            {"image": f"data:image/png;base64,{current_image}"}
                        ]
                    })
                    iteration_record["success"] = False
                    app_logger.warning(f"Tool {tool_name} failed: {error_msg}")
            
            iteration_record["duration"] = time.time() - iteration_start
            explorations.append(iteration_record)

            _emit("iteration.finished", {
                "iteration": iteration + 1,
                "success": iteration_record.get("success", True),
                "analysis_summary": iteration_record.get("analysis_summary", {}),
                "tool_name": iteration_record.get("tool_execution", {}).get("tool_name") if iteration_record.get("tool_execution") else None,
                "duration": iteration_record["duration"]
            })

            # 检查是否完成探索
            if analysis.get("exploration_complete", False):
                app_logger.info(f"Exploration complete at iteration {iteration + 1}")
                break
        
        # 保存messages和explorations到context
        if context is not None:
            context['autonomous_messages'] = messages
            context['autonomous_explorations'] = explorations
        
        # 生成最终报告
        final_report = self._generate_final_report(explorations)
        
        return {
            "success": True,
            "mode": "autonomous_exploration",
            "explorations": explorations,
            "final_report": final_report,
            "final_spec": current_spec,
            "final_image": current_image,
            "total_iterations": len(explorations)
        }

    def _extract_region(self, spec: Dict) -> Dict:
        """从 spec 中推测缩放区域（基于 encoding.scale.domain）。"""
        region = {}
        encoding = spec.get("encoding", {}) if isinstance(spec, dict) else {}
        x_enc = encoding.get("x", {}) if isinstance(encoding, dict) else {}
        y_enc = encoding.get("y", {}) if isinstance(encoding, dict) else {}

        def _parse_domain(dom):
            if isinstance(dom, list) and len(dom) == 2:
                try:
                    return float(dom[0]), float(dom[1])
                except Exception:  # noqa: BLE001
                    return None, None
            return None, None

        x_min, x_max = _parse_domain(x_enc.get("scale", {}).get("domain") if isinstance(x_enc.get("scale"), dict) else None)
        y_min, y_max = _parse_domain(y_enc.get("scale", {}).get("domain") if isinstance(y_enc.get("scale"), dict) else None)

        if x_min is not None or x_max is not None:
            region["x_min"] = x_min
            region["x_max"] = x_max
        if y_min is not None or y_max is not None:
            region["y_min"] = y_min
            region["y_max"] = y_max

        region["x_field"] = x_enc.get("field")
        region["y_field"] = y_enc.get("field")

        # 若没有任何区域信息，返回空 dict
        return region if any(v is not None for v in region.values()) else {}

    def _apply_data_manager(self, spec: Dict, context: Dict = None) -> Dict:
        """如果会话有 data_manager，则按区域补点后返回新的 spec。"""
        if not context:
            return spec

        data_manager = context.get("data_manager")
        session_id = context.get("session_id")
        if not data_manager or not session_id:
            return spec

        region = self._extract_region(spec)
        if not region:
            return spec

        try:
            current_count = get_spec_data_count(spec)
            new_values = data_manager.load_region(region)
            new_spec = copy.deepcopy(spec)
            new_spec.setdefault("data", {})["values"] = new_values
            app_logger.info(
                f"🔍 Region data loaded: {current_count} -> {len(new_values)} points "
                f"(region: x=[{region.get('x_min')}, {region.get('x_max')}], "
                f"y=[{region.get('y_min')}, {region.get('y_max')}])"
            )
            return new_spec
        except Exception as exc:  # noqa: BLE001
            app_logger.error(f"apply_data_manager failed: {exc}")
            return spec
    
    def _generate_final_report(self, explorations: List) -> Dict:
        """生成最终探索报告"""
        successful = [e for e in explorations if e.get("success")]
        
        all_insights = []
        tools_used = []
        
        for exp in successful:
            summary = exp.get("analysis_summary", {})
            all_insights.extend(summary.get("key_insights", []))
            
            if "tool_execution" in exp:
                tools_used.append({
                    "iteration": exp["iteration"],
                    "tool": exp["tool_execution"]["tool_name"],
                    "success": exp["tool_execution"]["tool_result"].get("success")
                })
        
        return {
            "total_iterations": len(explorations),
            "successful_iterations": len(successful),
            "all_insights": all_insights,
            "tools_used": tools_used,
            "summary": f"Completed {len(successful)}/{len(explorations)} exploration iterations"
        }
