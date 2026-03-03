"""
CSV to Vega/Vega-Lite Converter
支持将CSV数据转换为以下图表类型：
- 散点图 (Scatter Plot) - Vega-Lite
- 条形图 (Bar Chart) - Vega-Lite
- 折线图 (Line Chart) - Vega-Lite
- 平行坐标图 (Parallel Coordinates) - Vega-Lite
- 热力图 (Heatmap) - Vega-Lite
- 桑基图 (Sankey Diagram) - Vega
"""

import json
import pandas as pd
from typing import Optional, List, Dict, Any, Literal
from pathlib import Path


ChartType = Literal["scatter", "bar", "line", "parallel", "heatmap", "sankey"]


class VegaConverter:
    """CSV到Vega/Vega-Lite转换器"""
    
    def __init__(self, csv_path: str):
        """
        初始化转换器
        
        Args:
            csv_path: CSV文件路径
        """
        self.csv_path = csv_path
        self.dataset_name = Path(csv_path).stem
        self.df = pd.read_csv(csv_path)
        self.data = self.df.to_dict(orient="records")
        
        # 分析列类型
        self.numeric_cols = self.df.select_dtypes(include=['number']).columns.tolist()
        self.categorical_cols = self.df.select_dtypes(include=['object', 'category']).columns.tolist()
        self.datetime_cols = []
        
        # 尝试检测日期列
        for col in self.categorical_cols[:]:
            try:
                pd.to_datetime(self.df[col])
                self.datetime_cols.append(col)
                self.categorical_cols.remove(col)
            except:
                pass
    
    def get_column_info(self) -> Dict[str, List[str]]:
        """获取列信息"""
        return {
            "numeric": self.numeric_cols,
            "categorical": self.categorical_cols,
            "datetime": self.datetime_cols,
            "all": self.df.columns.tolist()
        }
    
    def convert(
        self,
        chart_type: ChartType,
        x: Optional[str] = None,
        y: Optional[str] = None,
        color: Optional[str] = None,
        size: Optional[str] = None,
        columns: Optional[List[str]] = None,
        normalize: bool = False,
        source: Optional[str] = None,
        target: Optional[str] = None,
        value: Optional[str] = None,
        title: Optional[str] = None,
        width: int = 600,
        height: int = 400
    ) -> Dict[str, Any]:
        """
        转换CSV为Vega/Vega-Lite规范
        
        Args:
            chart_type: 图表类型
            x: X轴字段
            y: Y轴字段
            color: 颜色编码字段
            size: 大小编码字段
            columns: 平行坐标图使用的列
            normalize: 平行坐标图是否归一化
            source: 桑基图源节点字段
            target: 桑基图目标节点字段
            value: 桑基图值字段
            title: 图表标题
            width: 图表宽度
            height: 图表高度
        
        Returns:
            Vega或Vega-Lite规范字典
        """
        if chart_type == "scatter":
            return self._create_scatter(x, y, color, size, title, width, height)
        elif chart_type == "bar":
            return self._create_bar(x, y, color, title, width, height)
        elif chart_type == "line":
            return self._create_line(x, y, color, title, width, height)
        elif chart_type == "parallel":
            return self._create_parallel_coordinates(columns, color, normalize, title, width, height)
        elif chart_type == "heatmap":
            return self._create_heatmap(x, y, color, title, width, height)
        elif chart_type == "sankey":
            return self._create_sankey(source, target, value, title, width, height)
        else:
            raise ValueError(f"不支持的图表类型: {chart_type}")
    
    def _auto_select_columns(self, prefer_numeric: bool = True, count: int = 2) -> List[str]:
        """自动选择合适的列"""
        if prefer_numeric and len(self.numeric_cols) >= count:
            return self.numeric_cols[:count]
        elif len(self.categorical_cols) >= 1 and len(self.numeric_cols) >= 1:
            return [self.categorical_cols[0], self.numeric_cols[0]]
        return self.df.columns.tolist()[:count]
    
    def _get_field_type(self, field: str) -> str:
        """获取字段的Vega-Lite类型"""
        if field in self.numeric_cols:
            return "quantitative"
        elif field in self.datetime_cols:
            return "temporal"
        elif field in self.categorical_cols:
            return "nominal"
        else:
            return "nominal"
    
    def _create_scatter(
        self,
        x: Optional[str],
        y: Optional[str],
        color: Optional[str],
        size: Optional[str],
        title: Optional[str],
        width: int,
        height: int
    ) -> Dict[str, Any]:
        """创建散点图 (Vega-Lite)"""
        cols = self._auto_select_columns(prefer_numeric=True, count=2)
        x = x or cols[0]
        y = y or (cols[1] if len(cols) > 1 else cols[0])
        
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title or f"Scatter Plot: {x} vs {y}",
            "width": width,
            "height": height,
            "data": {"values": self.data},
            "mark": {"type": "point", "filled": True, "opacity": 0.7},
            "encoding": {
                "x": {"field": x, "type": self._get_field_type(x)},
                "y": {"field": y, "type": self._get_field_type(y)}
            }
        }
        
        if color:
            spec["encoding"]["color"] = {
                "field": color,
                "type": self._get_field_type(color)
            }
        
        if size:
            spec["encoding"]["size"] = {
                "field": size,
                "type": self._get_field_type(size)
            }
        
        return spec
    
    def _create_bar(
        self,
        x: Optional[str],
        y: Optional[str],
        color: Optional[str],
        title: Optional[str],
        width: int,
        height: int
    ) -> Dict[str, Any]:
        """创建条形图 (Vega-Lite)"""
        # 优先选择一个分类列和一个数值列
        if not x:
            x = self.categorical_cols[0] if self.categorical_cols else self.df.columns[0]
        if not y:
            y = self.numeric_cols[0] if self.numeric_cols else self.df.columns[1] if len(self.df.columns) > 1 else self.df.columns[0]
        
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title or f"Bar Chart: {y} by {x}",
            "width": width,
            "height": height,
            "data": {"values": self.data},
            "mark": "bar",
            "encoding": {
                "x": {"field": x, "type": self._get_field_type(x)},
                "y": {"field": y, "type": self._get_field_type(y)}
            }
        }
        
        # 如果y是数值型，添加聚合
        if y in self.numeric_cols and x in self.categorical_cols:
            spec["encoding"]["y"]["aggregate"] = "mean"
        
        if color:
            spec["encoding"]["color"] = {
                "field": color,
                "type": self._get_field_type(color)
            }
        
        return spec
    
    def _create_line(
        self,
        x: Optional[str],
        y: Optional[str],
        color: Optional[str],
        title: Optional[str],
        width: int,
        height: int
    ) -> Dict[str, Any]:
        """创建折线图 (Vega-Lite)"""
        # 优先选择时间列或有序列作为x轴
        if not x:
            if self.datetime_cols:
                x = self.datetime_cols[0]
            elif self.categorical_cols:
                x = self.categorical_cols[0]
            else:
                x = self.df.columns[0]
        
        if not y:
            y = self.numeric_cols[0] if self.numeric_cols else self.df.columns[1] if len(self.df.columns) > 1 else self.df.columns[0]
        
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title or f"Line Chart: {y} over {x}",
            "width": width,
            "height": height,
            "data": {"values": self.data},
            "mark": {"type": "line", "point": True},
            "encoding": {
                "x": {"field": x, "type": self._get_field_type(x)},
                "y": {"field": y, "type": self._get_field_type(y)}
            }
        }
        
        if color:
            spec["encoding"]["color"] = {
                "field": color,
                "type": self._get_field_type(color)
            }
        
        return spec
    
    def _create_parallel_coordinates(
        self,
        columns: Optional[List[str]],
        color: Optional[str],
        normalize: bool,
        title: Optional[str],
        width: int,
        height: int
    ) -> Dict[str, Any]:
        """创建平行坐标图 (Vega-Lite)"""
        # 选择数值列用于平行坐标
        if not columns:
            columns = self.numeric_cols[:5] if len(self.numeric_cols) >= 2 else self.df.columns.tolist()[:5]
        
        if len(columns) < 2:
            raise ValueError("平行坐标图至少需要2个数值列")
        
        # 使用Vega-Lite的repeat和layer来创建平行坐标图
        # 首先需要将数据转换为长格式
        df_normalized = self.df[columns].copy()
        
        # 标准化数值以便在同一尺度上显示（可选）
        if normalize:
            for col in columns:
                if col in self.numeric_cols:
                    min_val = df_normalized[col].min()
                    max_val = df_normalized[col].max()
                    if max_val != min_val:
                        df_normalized[col] = (df_normalized[col] - min_val) / (max_val - min_val)
                    else:
                        df_normalized[col] = 0.5
        
        # 添加索引列
        df_normalized['_index'] = range(len(df_normalized))
        
        # 如果有颜色列，添加它
        if color and color in self.df.columns:
            df_normalized[color] = self.df[color]
        
        # 转换为长格式
        id_vars = ['_index']
        if color and color in df_normalized.columns and color not in columns:
            id_vars.append(color)
        
        # 确保value_vars中的列都存在
        valid_columns = [c for c in columns if c in df_normalized.columns]
        
        value_field = "normalized_value" if normalize else "value"
        df_long = df_normalized.melt(
            id_vars=id_vars,
            value_vars=valid_columns,
            var_name='dimension',
            value_name=value_field
        )
        
        # 生成每个维度的刻度数据（固定三档：min/mid/max）
        tick_records = []
        axis_records = []
        for col in valid_columns:
            axis_records.append({"dimension": col})
            if normalize:
                series = self.df[col]
                min_val = float(series.min())
                max_val = float(series.max())
                median_val = float(series.median())
                tick_map = {
                    "min": {"value": 0.0, "label": min_val},
                    "mid": {"value": 0.5, "label": median_val},
                    "max": {"value": 1.0, "label": max_val}
                }
            else:
                series = self.df[col]
                min_val = float(series.min())
                max_val = float(series.max())
                mid_val = (min_val + max_val) / 2
                tick_map = {
                    "min": {"value": min_val, "label": min_val},
                    "mid": {"value": mid_val, "label": mid_val},
                    "max": {"value": max_val, "label": max_val}
                }
            
            for level, tick_info in tick_map.items():
                tick_records.append({
                    "dimension": col,
                    "tick_level": level,
                    "tick_value": float(tick_info["value"]),
                    "tick_label": float(tick_info["label"])
                })
        
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title or f"Parallel: {self.dataset_name}",
            "width": width,
            "height": height,
            "data": {"values": df_long.to_dict(orient="records")},
            "encoding": {
                "x": {
                    "field": "dimension",
                    "type": "nominal",
                    "sort": valid_columns,
                    "axis": {"title": None, "labelAngle": 0}
                }
            },
            "layer": [
                {
                    "data": {"values": axis_records},
                    "mark": {"type": "rule", "color": "#ccc"},
                    "encoding": {}
                },
                {
                    "mark": {"type": "line", "opacity": 0.3, "strokeWidth": 1},
                    "encoding": {
                        "y": {
                            "field": value_field,
                            "type": "quantitative",
                            "axis": None
                        },
                        "detail": {"field": "_index", "type": "nominal"}
                    }
                },
                {
                    "data": {"values": tick_records},
                    "transform": [{"filter": "datum.tick_level === 'max'"}],
                    "encoding": {
                        "y": {
                            "field": "tick_value",
                            "type": "quantitative",
                            "axis": None
                        }
                    },
                    "layer": [
                        {
                            "mark": {"type": "text", "style": "label"},
                            "encoding": {"text": {"field": "tick_label", "type": "quantitative"}}
                        },
                        {
                            "mark": {"type": "tick", "style": "tick", "size": 8, "color": "#ccc"}
                        }
                    ]
                },
                {
                    "data": {"values": tick_records},
                    "transform": [{"filter": "datum.tick_level === 'mid'"}],
                    "encoding": {
                        "y": {
                            "field": "tick_value",
                            "type": "quantitative",
                            "axis": None
                        }
                    },
                    "layer": [
                        {
                            "mark": {"type": "text", "style": "label"},
                            "encoding": {"text": {"field": "tick_label", "type": "quantitative"}}
                        },
                        {
                            "mark": {"type": "tick", "style": "tick", "size": 8, "color": "#ccc"}
                        }
                    ]
                },
                {
                    "data": {"values": tick_records},
                    "transform": [{"filter": "datum.tick_level === 'min'"}],
                    "encoding": {
                        "y": {
                            "field": "tick_value",
                            "type": "quantitative",
                            "axis": None
                        }
                    },
                    "layer": [
                        {
                            "mark": {"type": "text", "style": "label"},
                            "encoding": {"text": {"field": "tick_label", "type": "quantitative"}}
                        },
                        {
                            "mark": {"type": "tick", "style": "tick", "size": 8, "color": "#ccc"}
                        }
                    ]
                }
            ],
            "config": {
                "axisX": {"domain": False, "labelAngle": 0, "tickColor": "#ccc", "title": None},
                "view": {"stroke": None},
                "style": {
                    "label": {"baseline": "middle", "align": "right", "dx": -5},
                    "tick": {"orient": "horizontal"}
                }
            }
        }
        
        # 添加颜色编码
        if color and color in df_long.columns:
            spec["layer"][1]["encoding"]["color"] = {
                "field": color,
                "type": self._get_field_type(color)
            }
            spec["layer"][1]["mark"]["opacity"] = 0.5
        
        return spec
    
    def _create_heatmap(
        self,
        x: Optional[str],
        y: Optional[str],
        color: Optional[str],
        title: Optional[str],
        width: int,
        height: int
    ) -> Dict[str, Any]:
        """创建热力图 (Vega-Lite)"""
        # 选择两个分类列和一个数值列
        if not x:
            x = self.categorical_cols[0] if self.categorical_cols else self.df.columns[0]
        if not y:
            y = self.categorical_cols[1] if len(self.categorical_cols) > 1 else (
                self.categorical_cols[0] if self.categorical_cols else self.df.columns[1] if len(self.df.columns) > 1 else self.df.columns[0]
            )
        if not color:
            color = self.numeric_cols[0] if self.numeric_cols else "count"
        
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title or f"Heatmap: {color} by {x} and {y}",
            "width": width,
            "height": height,
            "data": {"values": self.data},
            "mark": "rect",
            "encoding": {
                "x": {"field": x, "type": "nominal"},
                "y": {"field": y, "type": "nominal"},
                "color": {
                    "aggregate": "mean" if color in self.numeric_cols else "count",
                    "field": color if color != "count" else None,
                    "type": "quantitative",
                    "scale": {"scheme": "blues"}
                }
            }
        }
        
        # 如果color是count，移除field
        if color == "count":
            spec["encoding"]["color"] = {
                "aggregate": "count",
                "type": "quantitative",
                "scale": {"scheme": "blues"}
            }
        
        return spec
    
    def _create_sankey(
        self,
        source: Optional[str],
        target: Optional[str],
        value: Optional[str],
        title: Optional[str],
        width: int,
        height: int
    ) -> Dict[str, Any]:
        """创建桑基图 (Vega)"""
        # 桑基图需要source, target, value三列
        if not source:
            source = self.categorical_cols[0] if self.categorical_cols else self.df.columns[0]
        if not target:
            target = self.categorical_cols[1] if len(self.categorical_cols) > 1 else self.df.columns[1] if len(self.df.columns) > 1 else self.df.columns[0]
        if not value:
            value = self.numeric_cols[0] if self.numeric_cols else None
        
        # 准备桑基图数据
        # 聚合相同source-target对的值
        if value:
            df_sankey = self.df.groupby([source, target])[value].sum().reset_index()
        else:
            df_sankey = self.df.groupby([source, target]).size().reset_index(name='value')
            value = 'value'
        
        # 获取所有唯一节点
        nodes = list(set(df_sankey[source].tolist() + df_sankey[target].tolist()))
        node_map = {node: idx for idx, node in enumerate(nodes)}
        
        # 转换数据格式
        links_data = []
        for _, row in df_sankey.iterrows():
            links_data.append({
                "source": node_map[row[source]],
                "target": node_map[row[target]],
                "value": float(row[value])
            })
        
        nodes_data = [{"name": node} for node in nodes]
        
        spec = {
            "$schema": "https://vega.github.io/schema/vega/v5.json",
            "title": {"text": title or f"Sankey Diagram: {source} → {target}"},
            "width": width,
            "height": height,
            "padding": 10,
            "data": [
                {
                    "name": "nodes",
                    "values": nodes_data,
                    "transform": [
                        {"type": "identifier", "as": "id"}
                    ]
                },
                {
                    "name": "links",
                    "values": links_data
                }
            ],
            "scales": [
                {
                    "name": "color",
                    "type": "ordinal",
                    "domain": {"data": "nodes", "field": "name"},
                    "range": {"scheme": "category20"}
                }
            ],
            "marks": [
                {
                    "type": "group",
                    "from": {
                        "facet": {
                            "name": "sankey",
                            "data": "links",
                            "transform": [
                                {
                                    "type": "sankey",
                                    "extent": [{"signal": "[0, 0]"}, {"signal": "[width, height]"}],
                                    "nodeId": {"expr": "datum.id"},
                                    "nodeWidth": 10,
                                    "nodePadding": 10,
                                    "nodes": "nodes",
                                    "links": "links"
                                }
                            ]
                        }
                    },
                    "marks": [
                        {
                            "type": "path",
                            "from": {"data": "sankey"},
                            "clip": True,
                            "encode": {
                                "enter": {
                                    "stroke": {"scale": "color", "field": "source.name"},
                                    "strokeWidth": {"field": "width"},
                                    "strokeOpacity": {"value": 0.5}
                                },
                                "update": {
                                    "path": {"field": "path"}
                                }
                            }
                        }
                    ]
                },
                {
                    "type": "rect",
                    "from": {"data": "nodes"},
                    "encode": {
                        "enter": {
                            "x": {"field": "x0"},
                            "x2": {"field": "x1"},
                            "y": {"field": "y0"},
                            "y2": {"field": "y1"},
                            "fill": {"scale": "color", "field": "name"},
                            "stroke": {"value": "#000"},
                            "strokeWidth": {"value": 0.5}
                        }
                    }
                },
                {
                    "type": "text",
                    "from": {"data": "nodes"},
                    "encode": {
                        "enter": {
                            "x": {"signal": "datum.x0 < width / 2 ? datum.x1 + 5 : datum.x0 - 5"},
                            "y": {"signal": "(datum.y0 + datum.y1) / 2"},
                            "align": {"signal": "datum.x0 < width / 2 ? 'left' : 'right'"},
                            "baseline": {"value": "middle"},
                            "text": {"field": "name"},
                            "fontSize": {"value": 10}
                        }
                    }
                }
            ]
        }
        
        return spec
    
    def save_spec(self, spec: Dict[str, Any], output_path: str) -> str:
        """
        保存规范到JSON文件
        
        Args:
            spec: Vega/Vega-Lite规范
            output_path: 输出文件路径
        
        Returns:
            保存的文件路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(spec, f, indent=2, ensure_ascii=False)
        
        return str(output_path)


def convert_csv_to_vega(
    csv_path: str,
    chart_type: ChartType,
    output_path: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    便捷函数：将CSV转换为Vega/Vega-Lite规范
    
    Args:
        csv_path: CSV文件路径
        chart_type: 图表类型 ("scatter", "bar", "line", "parallel", "heatmap", "sankey")
        output_path: 输出JSON文件路径（可选）
        **kwargs: 其他参数传递给convert方法
    
    Returns:
        Vega/Vega-Lite规范字典
    """
    converter = VegaConverter(csv_path)
    spec = converter.convert(chart_type, **kwargs)
    
    if output_path:
        converter.save_spec(spec, output_path)
    
    return spec


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="CSV to Vega/Vega-Lite Converter")
    parser.add_argument("csv_path", help="输入CSV文件路径")
    parser.add_argument("chart_type", choices=["scatter", "bar", "line", "parallel", "heatmap", "sankey"],
                       help="图表类型")
    parser.add_argument("-o", "--output", help="输出JSON文件路径")
    parser.add_argument("--x", help="X轴字段")
    parser.add_argument("--y", help="Y轴字段")
    parser.add_argument("--color", help="颜色编码字段")
    parser.add_argument("--size", help="大小编码字段（仅散点图）")
    parser.add_argument("--columns", nargs="+", help="平行坐标图使用的列")
    parser.add_argument("--normalize", action="store_true", help="平行坐标图是否归一化（默认关闭）")
    parser.add_argument("--source", help="桑基图源节点字段")
    parser.add_argument("--target", help="桑基图目标节点字段")
    parser.add_argument("--value", help="桑基图值字段")
    parser.add_argument("--title", help="图表标题")
    parser.add_argument("--width", type=int, default=600, help="图表宽度")
    parser.add_argument("--height", type=int, default=400, help="图表高度")
    
    args = parser.parse_args()
    
    spec = convert_csv_to_vega(
        csv_path=args.csv_path,
        chart_type=args.chart_type,
        output_path=args.output,
        x=args.x,
        y=args.y,
        color=args.color,
        size=args.size,
        columns=args.columns,
        normalize=args.normalize,
        source=args.source,
        target=args.target,
        value=args.value,
        title=args.title,
        width=args.width,
        height=args.height
    )
    
    if not args.output:
        print(json.dumps(spec, indent=2, ensure_ascii=False))
